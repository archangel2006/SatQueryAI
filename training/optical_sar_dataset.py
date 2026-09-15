from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Iterable

import lmdb
import numpy as np
import pandas as pd
import torch
from safetensors.numpy import load as load_safetensors
from torch import Tensor
from torch.utils.data import Dataset

_LMDB_ENVS: dict[str, lmdb.Environment] = {}

OPTICAL_BANDS = ("B02", "B03", "B04", "B08")
SAR_BANDS = ("VV", "VH")


def parse_labels(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (list, tuple, set)):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def patch_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one row per patch with a normalised split and parsed labels."""
    if "patch_id" not in frame.columns:
        raise ValueError("Metadata is missing required column: patch_id")
    split_col = next(
        (c for c in ("split", "split_text") if c in frame.columns), None
    )
    if split_col is None:
        raise ValueError("Metadata needs a 'split' or 'split_text' column.")

    keep = [c for c in ("patch_id", "s1_name", "labels", "contains_cloud_or_shadow", split_col) if c in frame.columns]
    result = frame[keep].copy().dropna(subset=["patch_id"]).drop_duplicates("patch_id").reset_index(drop=True)

    result["labels"] = result["labels"].map(parse_labels) if "labels" in result.columns else [[] for _ in range(len(result))]
    if "contains_cloud_or_shadow" in result.columns:
        result["contains_cloud_or_shadow"] = result["contains_cloud_or_shadow"].map(parse_bool)
    result["split"] = result[split_col].astype(str).str.lower().replace({"validation": "val"})
    result = result[result["split"].isin({"train", "val", "test"})].reset_index(drop=True)
    return result


def label_vocabulary(frame: pd.DataFrame) -> list[str]:
    return sorted({label for labels in frame["labels"] for label in labels})


def _find_array(payload: dict[str, np.ndarray], names: Iterable[str]) -> np.ndarray | None:
    normalized = {k.lower(): v for k, v in payload.items()}
    for name in names:
        v = normalized.get(name.lower())
        if v is not None:
            return np.asarray(v)
    return None


def _stack_bands(payload: dict[str, np.ndarray], bands: tuple[str, ...], name: str) -> np.ndarray:
    arrays = [_find_array(payload, (b,)) for b in bands]
    missing = [b for b, a in zip(bands, arrays) if a is None]
    if missing:
        raise KeyError(f"{name} payload is missing bands: {missing}")
    shapes = {a.shape for a in arrays if a is not None}
    if len(shapes) != 1:
        raise ValueError(f"{name} bands have inconsistent shapes: {sorted(shapes)}")
    return np.stack([a.astype(np.float32) for a in arrays], axis=0)  # type: ignore[arg-type]


def _normalize_channels(array: np.ndarray) -> Tensor:
    tensor = torch.from_numpy(array.astype(np.float32, copy=False))
    finite = torch.isfinite(tensor)
    tensor = torch.nan_to_num(tensor, nan=0.0, posinf=0.0, neginf=0.0)
    for c in range(tensor.shape[0]):
        vals = tensor[c][finite[c]]
        if vals.numel() == 0:
            continue
        lo, hi = torch.quantile(vals, torch.tensor([0.02, 0.98]))
        if hi > lo:
            tensor[c] = ((tensor[c] - lo) / (hi - lo)).clamp(0.0, 1.0)
    return tensor


class BigEarthNetFusionDataset(Dataset[dict[str, Any]]):
    """Paired S1+S2 BigEarthNet-MM dataset for multilabel classification.

    Expects an LMDB where each record keyed by the S2 patch_id contains
    both optical bands (B02, B03, B04, B08) and SAR bands (VV, VH),
    or SAR stored under a separate s1_name key.
    """

    def __init__(
        self,
        metadata_path: str | Path,
        lmdb_path: str | Path,
        split: str,
        label_names: list[str] | None = None,
        target_size: tuple[int, int] | None = (120, 120),
    ) -> None:
        raw = pd.read_csv(metadata_path) if str(metadata_path).endswith(".csv") else pd.read_parquet(metadata_path)
        self.metadata = patch_metadata(raw)
        split_name = "val" if split == "validation" else split
        self.metadata = self.metadata[self.metadata["split"] == split_name].reset_index(drop=True)
        if self.metadata.empty:
            raise ValueError(f"No rows found for split '{split}'.")
        self.label_names = label_names or label_vocabulary(self.metadata)
        self.label_to_index = {label: i for i, label in enumerate(self.label_names)}
        self.lmdb_path = str(lmdb_path)
        self.target_size = target_size

    def __len__(self) -> int:
        return len(self.metadata)

    def _env(self) -> lmdb.Environment:
        if self.lmdb_path not in _LMDB_ENVS:
            _LMDB_ENVS[self.lmdb_path] = lmdb.open(
                self.lmdb_path, readonly=True, lock=False,
                readahead=False, meminit=False, max_readers=126,
            )
        return _LMDB_ENVS[self.lmdb_path]

    def _payload(self, key: str) -> dict[str, np.ndarray]:
        with self._env().begin(write=False) as txn:
            raw = txn.get(key.encode())
        if raw is None:
            raise KeyError(f"No LMDB record for key '{key}'.")
        return {str(k): np.asarray(v) for k, v in load_safetensors(raw).items()}

    def _load_modalities(self, row: pd.Series) -> tuple[np.ndarray, np.ndarray]:
        patch_id = str(row["patch_id"])
        payload = self._payload(patch_id)
        optical = _stack_bands(payload, OPTICAL_BANDS, "Optical")
        keys = {k.lower() for k in payload}
        if all(b.lower() in keys for b in SAR_BANDS):
            sar = _stack_bands(payload, SAR_BANDS, "SAR")
        else:
            s1_name = str(row["s1_name"]) if "s1_name" in row.index and pd.notna(row.get("s1_name")) else ""
            if not s1_name or s1_name == "nan":
                raise KeyError(
                    f"Patch '{patch_id}' has no SAR bands and no s1_name. "
                    "Use a paired S1+S2 LMDB (BigEarthNet-MM)."
                )
            sar = _stack_bands(self._payload(s1_name), SAR_BANDS, "SAR")
        return optical, sar

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.metadata.iloc[index]
        optical, sar = self._load_modalities(row)
        optical_t = _normalize_channels(optical)
        sar_t = _normalize_channels(sar)
        if self.target_size is not None:
            optical_t = torch.nn.functional.interpolate(optical_t.unsqueeze(0), size=self.target_size, mode="bilinear", align_corners=False).squeeze(0)
            sar_t = torch.nn.functional.interpolate(sar_t.unsqueeze(0), size=self.target_size, mode="bilinear", align_corners=False).squeeze(0)
        target = torch.zeros(len(self.label_names), dtype=torch.float32)
        for label in row["labels"]:
            if label in self.label_to_index:
                target[self.label_to_index[label]] = 1.0
        return {
            "optical": optical_t,
            "sar": sar_t,
            "label": target,
            "patch_id": str(row["patch_id"]),
            "labels": row["labels"],
            "contains_cloud_or_shadow": bool(row.get("contains_cloud_or_shadow", False)),
        }

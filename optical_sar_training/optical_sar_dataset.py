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
    """Parse BigEarthNet multilabel values from common CSV representations."""
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
    """Parse common boolean values used by metadata exports."""
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def patch_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one metadata row per patch with a normalized split and labels."""
    required = {"patch_id", "labels"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Metadata is missing required columns: {sorted(missing)}")
    split_column = "split" if "split" in frame.columns else "split_text" if "split_text" in frame.columns else None
    if split_column is None:
        raise ValueError("Metadata needs a split or split_text column.")

    columns = [
        column
        for column in (
            "patch_id",
            "s1_name",
            "s2v1_name",
            "labels",
            "contains_cloud_or_shadow",
            split_column,
        )
        if column in frame
    ]
    result = frame[columns].copy()
    result = result.dropna(subset=["patch_id"]).drop_duplicates("patch_id").reset_index(drop=True)
    result["labels"] = result["labels"].map(parse_labels)
    if "contains_cloud_or_shadow" in result:
        result["contains_cloud_or_shadow"] = result["contains_cloud_or_shadow"].map(parse_bool)
    result["split"] = result[split_column].astype(str).str.lower()
    result = result[result["split"].isin({"train", "validation", "val", "test", "bench"})]
    result["split"] = result["split"].replace({"validation": "val"})
    return result.reset_index(drop=True)


def label_vocabulary(frame: pd.DataFrame) -> list[str]:
    """Build a stable scene-label vocabulary from normalized metadata."""
    return sorted({label for labels in frame["labels"] for label in labels})


def _find_array(payload: dict[str, np.ndarray], names: Iterable[str]) -> np.ndarray | None:
    normalized = {key.lower(): value for key, value in payload.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return np.asarray(value)
    return None


def _stack_bands(payload: dict[str, np.ndarray], bands: tuple[str, ...], name: str) -> np.ndarray:
    arrays = [_find_array(payload, (band,)) for band in bands]
    if any(array is None for array in arrays):
        missing = [band for band, array in zip(bands, arrays) if array is None]
        raise KeyError(f"{name} payload is missing bands: {missing}")
    shapes = {array.shape for array in arrays if array is not None}
    if len(shapes) != 1:
        raise ValueError(f"{name} bands do not share one spatial shape: {sorted(shapes)}")
    return np.stack([array.astype(np.float32) for array in arrays], axis=0)


def _normalize_channels(array: np.ndarray) -> Tensor:
    tensor = torch.from_numpy(array.astype(np.float32, copy=False))
    finite = torch.isfinite(tensor)
    tensor = torch.nan_to_num(tensor, nan=0.0, posinf=0.0, neginf=0.0)
    for channel in range(tensor.shape[0]):
        values = tensor[channel][finite[channel]]
        if values.numel() == 0:
            continue
        low, high = torch.quantile(values, torch.tensor([0.02, 0.98], device=values.device))
        if high > low:
            tensor[channel] = ((tensor[channel] - low) / (high - low)).clamp(0.0, 1.0)
    return tensor


class BigEarthNetFusionDataset(Dataset[dict[str, Any]]):
    """Load one S1/S2 patch and scene-level multilabel target per sample."""

    def __init__(
        self,
        metadata_path: str | Path,
        lmdb_path: str | Path,
        split: str,
        label_names: list[str] | None = None,
        target_size: tuple[int, int] | None = (120, 120),
    ) -> None:
        self.metadata = patch_metadata(pd.read_csv(metadata_path) if str(metadata_path).endswith(".csv") else pd.read_parquet(metadata_path))
        split_name = "val" if split == "validation" else split
        self.metadata = self.metadata[self.metadata["split"] == split_name].reset_index(drop=True)
        if self.metadata.empty:
            raise ValueError(f"No rows found for split '{split}'.")
        self.label_names = label_names or label_vocabulary(self.metadata)
        self.label_to_index = {label: index for index, label in enumerate(self.label_names)}
        self.lmdb_path = str(lmdb_path)
        self.target_size = target_size
    def __len__(self) -> int:
        return len(self.metadata)

    def _environment(self) -> lmdb.Environment:
        path = str(self.lmdb_path)

        if path not in _LMDB_ENVS:
            _LMDB_ENVS[path] = lmdb.open(
                path,
                readonly=True,
                lock=False,
                readahead=False,
                meminit=False,
                max_readers=126,
            )

        return _LMDB_ENVS[path]

    def _payload(self, key: str) -> dict[str, np.ndarray]:
        with self._environment().begin(write=False) as transaction:
            raw = transaction.get(str(key).encode())
        if raw is None:
            raise KeyError(f"No LMDB record found for key '{key}'.")
        return {str(name): np.asarray(array) for name, array in load_safetensors(raw).items()}

    @staticmethod
    def _has_bands(payload: dict[str, np.ndarray], bands: tuple[str, ...]) -> bool:
        keys = {key.lower() for key in payload}
        return all(band.lower() in keys for band in bands)

    def _load_modalities(self, row: pd.Series) -> tuple[np.ndarray, np.ndarray]:
        patch_id = str(row["patch_id"])
        combined = self._payload(patch_id)
        optical = _stack_bands(combined, OPTICAL_BANDS, "Optical")
        if self._has_bands(combined, SAR_BANDS):
            sar = _stack_bands(combined, SAR_BANDS, "SAR")
        else:
            s1_name = str(row.get("s1_name", ""))
            if not s1_name or s1_name == "nan":
                raise KeyError(f"Patch '{patch_id}' has no s1_name for a separate SAR record.")
            sar = _stack_bands(self._payload(s1_name), SAR_BANDS, "SAR")
        return optical, sar

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.metadata.iloc[index]
        optical, sar = self._load_modalities(row)
        optical_tensor = _normalize_channels(optical)
        sar_tensor = _normalize_channels(sar)
        if optical_tensor.shape[-2:] != sar_tensor.shape[-2:]:
            raise ValueError(f"Patch '{row['patch_id']}' has unaligned S1/S2 shapes.")
        if self.target_size is not None:
            size = self.target_size
            optical_tensor = torch.nn.functional.interpolate(optical_tensor.unsqueeze(0), size=size, mode="bilinear", align_corners=False).squeeze(0)
            sar_tensor = torch.nn.functional.interpolate(sar_tensor.unsqueeze(0), size=size, mode="bilinear", align_corners=False).squeeze(0)
        target = torch.zeros(len(self.label_names), dtype=torch.float32)
        for label in row["labels"]:
            if label in self.label_to_index:
                target[self.label_to_index[label]] = 1.0
        return {
            "optical": optical_tensor,
            "sar": sar_tensor,
            "label": target,
            "patch_id": str(row["patch_id"]),
            "labels": row["labels"],
            "contains_cloud_or_shadow": bool(row.get("contains_cloud_or_shadow", False)),
        }
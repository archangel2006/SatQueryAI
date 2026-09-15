from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import rasterio
import torch
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window
from torch import Tensor
from torch.utils.data import Dataset

# Documented S1S2-Water storage scale factors
S1_STORAGE_SCALE: float = 100.0       # int16 / 100.0 -> dB values
S2_STORAGE_SCALE: float = 10_000.0    # uint16 / 10000.0 -> reflectance [0.0, 1.0]

# Standard reference bands
S1_BANDS = ("VV", "VH")
S2_BANDS = ("B02_Blue", "B03_Green", "B04_Red", "B08_NIR", "B11_SWIR1", "B12_SWIR2")


@dataclass(frozen=True)
class NormalizationConfig:
    """Documented, reproducible, deterministic normalization configuration.

    Applied AFTER scale factors (S1 / 100.0, S2 / 10000.0).
    Modes:
      - 'minmax': Fixed physical range clipping and linear scaling to [0.0, 1.0].
      - 'standard': Fixed mean & standard deviation z-score standardization.
      - 'raw': No additional scaling beyond the storage scale factors.
    """

    mode: str = "minmax"
    # S1 minmax physical clipping ranges (in dB)
    s1_min: tuple[float, float] = (-30.0, -35.0)  # VV, VH lower bounds
    s1_max: tuple[float, float] = (0.0, -5.0)     # VV, VH upper bounds

    # S2 minmax reflectance range
    s2_min: float = 0.0
    s2_max: float = 1.0

    # S1 standard normalization stats (means, stds in dB)
    s1_means: tuple[float, float] = (-12.0, -19.0)
    s1_stds: tuple[float, float] = (5.5, 5.5)

    # S2 standard normalization stats (6 bands: Blue, Green, Red, NIR, SWIR1, SWIR2)
    s2_means: tuple[float, ...] = (0.135, 0.130, 0.125, 0.280, 0.210, 0.145)
    s2_stds: tuple[float, ...] = (0.090, 0.090, 0.095, 0.140, 0.120, 0.095)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizationConfig:
        return cls(
            mode=data.get("mode", "minmax"),
            s1_min=tuple(data.get("s1_min", (-30.0, -35.0))),
            s1_max=tuple(data.get("s1_max", (0.0, -5.0))),
            s2_min=float(data.get("s2_min", 0.0)),
            s2_max=float(data.get("s2_max", 1.0)),
            s1_means=tuple(data.get("s1_means", (-12.0, -19.0))),
            s1_stds=tuple(data.get("s1_stds", (5.5, 5.5))),
            s2_means=tuple(data.get("s2_means", (0.135, 0.130, 0.125, 0.280, 0.210, 0.145))),
            s2_stds=tuple(data.get("s2_stds", (0.090, 0.090, 0.095, 0.140, 0.120, 0.095))),
        )


DEFAULT_NORM_CONFIG = NormalizationConfig()


def normalize_s1(s1_db: np.ndarray, config: NormalizationConfig = DEFAULT_NORM_CONFIG) -> np.ndarray:
    """Normalize 2-band S1 dB array [2, H, W] deterministically."""
    out = np.nan_to_num(s1_db, nan=0.0, posinf=0.0, neginf=0.0).copy()
    if config.mode == "raw":
        return out
    if config.mode == "standard":
        for c in range(min(2, out.shape[0])):
            mean = config.s1_means[c]
            std = config.s1_stds[c] if config.s1_stds[c] > 1e-6 else 1.0
            out[c] = (out[c] - mean) / std
        return out

    # Default 'minmax'
    for c in range(min(2, out.shape[0])):
        lo = config.s1_min[c]
        hi = config.s1_max[c]
        denom = hi - lo if hi > lo else 1.0
        out[c] = np.clip((out[c] - lo) / denom, 0.0, 1.0)
    return out


def normalize_s2(s2_refl: np.ndarray, config: NormalizationConfig = DEFAULT_NORM_CONFIG) -> np.ndarray:
    """Normalize 6-band S2 reflectance array [6, H, W] deterministically."""
    out = np.nan_to_num(s2_refl, nan=0.0, posinf=0.0, neginf=0.0).copy()
    if config.mode == "raw":
        return out
    if config.mode == "standard":
        for c in range(min(len(config.s2_means), out.shape[0])):
            mean = config.s2_means[c]
            std = config.s2_stds[c] if config.s2_stds[c] > 1e-6 else 1.0
            out[c] = (out[c] - mean) / std
        return out

    # Default 'minmax'
    lo = config.s2_min
    hi = config.s2_max
    denom = hi - lo if hi > lo else 1.0
    return np.clip((out - lo) / denom, 0.0, 1.0)


@dataclass(frozen=True)
class ScenePaths:
    sample_id: str
    s1_img: Path
    s1_msk: Path
    s1_valid: Path
    s2_img: Path
    s2_msk: Path
    s2_valid: Path
    meta: Path


def _natural_sort_key(s: str) -> tuple[int, Any]:
    """Sort key that orders numerical folder names by integer value."""
    match = re.match(r"^(\d+)$", s)
    if match:
        return (0, int(match.group(1)))
    return (1, s)


def _scene_paths(root_dir: Path, sample_id: str) -> ScenePaths:
    scene_dir = root_dir / sample_id
    sid = sample_id
    return ScenePaths(
        sample_id=sid,
        s1_img=scene_dir / f"sentinel12_s1_{sid}_img.tif",
        s1_msk=scene_dir / f"sentinel12_s1_{sid}_msk.tif",
        s1_valid=scene_dir / f"sentinel12_s1_{sid}_valid.tif",
        s2_img=scene_dir / f"sentinel12_s2_{sid}_img.tif",
        s2_msk=scene_dir / f"sentinel12_s2_{sid}_msk.tif",
        s2_valid=scene_dir / f"sentinel12_s2_{sid}_valid.tif",
        meta=scene_dir / f"sentinel12_{sid}_meta.json",
    )


def discover_scene_ids(root_dir: str | Path) -> list[str]:
    """Discover all valid scene subdirectories under root_dir.

    Does not assume consecutive IDs. Sorts naturally so '1', '5', '6', '10'
    appear in natural numerical order.
    """
    path = Path(root_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"Dataset root does not exist: {path}")

    sample_ids: list[str] = []
    for child in sorted(path.iterdir(), key=lambda p: _natural_sort_key(p.name)):
        if not child.is_dir():
            continue
        paths = _scene_paths(path, child.name)
        if paths.s2_img.is_file() and paths.s1_img.is_file():
            sample_ids.append(child.name)
    return sample_ids


def inspect_scene_availability(
    root_dir: str | Path,
    requested_ids: Sequence[int | str],
) -> dict[str, list[str]]:
    """Check which requested scene IDs exist with all required files."""
    path = Path(root_dir)
    req_str = [str(sid) for sid in requested_ids]
    available: list[str] = []
    missing: list[str] = []

    for sid in req_str:
        paths = _scene_paths(path, sid)
        required = (
            paths.s1_img,
            paths.s1_valid,
            paths.s2_img,
            paths.s2_msk,
            paths.s2_valid,
        )
        if all(p.is_file() for p in required):
            available.append(sid)
        else:
            missing.append(sid)

    return {
        "requested": req_str,
        "available": available,
        "missing": missing,
    }


def inspect_s1_mask(s1_msk_path: Path, window: Window | None = None) -> dict[str, Any]:
    """Inspect and document the S1 *_msk.tif file.

    In S1S2-Water, sentinel12_s1_<id>_msk.tif is also provided alongside
    the S2 mask. This function allows inspecting its metadata and values.
    """
    if not s1_msk_path.is_file():
        return {"exists": False, "path": str(s1_msk_path)}

    with rasterio.open(s1_msk_path) as src:
        data = src.read(1, window=window)
        unique_vals = np.unique(data).tolist()
        return {
            "exists": True,
            "path": str(s1_msk_path),
            "crs": str(src.crs),
            "res": src.res,
            "shape": (src.height, src.width),
            "unique_values": unique_vals,
            "min": float(data.min()),
            "max": float(data.max()),
            "non_zero_count": int(np.count_nonzero(data)),
        }


def _normalize_split(name: str) -> str:
    split = name.strip().lower()
    if split == "validation":
        return "val"
    return split


def _read_scene_split(meta_path: Path) -> str | None:
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        split = payload.get("properties", {}).get("split")
        if split is None:
            split = payload.get("split")
        return _normalize_split(str(split)) if split is not None else None
    except Exception:
        return None


def align_windowed_s1_to_s2(
    s1_img_path: Path,
    s1_valid_path: Path,
    s2_src: rasterio.DatasetReader,
    s2_window: Window,
    patch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Geospatially align windowed S1 SAR and valid mask to the S2 patch grid.

    Steps (per PS 26167 specification):
      1. Determine geographic bounds of the S2 patch.
      2. Transform bounds to S1 coordinate system (if CRSs differ).
      3. Compute S1 window with a 2-pixel margin for interpolation borders.
      4. Read ONLY that windowed chunk from S1 image and S1 valid mask.
      5. Reproject S1 (bilinear) and S1 valid (nearest) to the S2 patch grid.

    Memory Safety:
      Never loads the full 12200x12200 S1 raster. Only the required window (~280x280)
      is read and resampled.
    """
    s2_bounds = rasterio.windows.bounds(s2_window, s2_src.transform)
    s2_win_transform = s2_src.window_transform(s2_window)
    s2_crs = s2_src.crs

    with rasterio.open(s1_img_path) as s1_src:
        s1_crs = s1_src.crs
        if s1_crs != s2_crs:
            s1_bounds = transform_bounds(s2_crs, s1_crs, *s2_bounds)
        else:
            s1_bounds = s2_bounds

        # Compute S1 pixel window with 2-pixel border margin
        raw_s1_win = rasterio.windows.from_bounds(*s1_bounds, transform=s1_src.transform)
        col_start = max(0, int(np.floor(raw_s1_win.col_off)) - 2)
        row_start = max(0, int(np.floor(raw_s1_win.row_off)) - 2)
        col_end = min(s1_src.width, int(np.ceil(raw_s1_win.col_off + raw_s1_win.width)) + 2)
        row_end = min(s1_src.height, int(np.ceil(raw_s1_win.row_off + raw_s1_win.height)) + 2)

        win_w = max(1, col_end - col_start)
        win_h = max(1, row_end - row_start)
        s1_window = Window(col_start, row_start, win_w, win_h)

        # Read only windowed chunk into memory
        s1_patch_raw = s1_src.read(window=s1_window).astype(np.float32)
        s1_win_transform = s1_src.window_transform(s1_window)

        # Reproject 2 S1 SAR bands (VV, VH) onto exact S2 patch grid
        s1_aligned = np.zeros((2, patch_size, patch_size), dtype=np.float32)
        for b in range(min(2, s1_patch_raw.shape[0])):
            reproject(
                source=s1_patch_raw[b],
                destination=s1_aligned[b],
                src_transform=s1_win_transform,
                src_crs=s1_crs,
                dst_transform=s2_win_transform,
                dst_crs=s2_crs,
                resampling=Resampling.bilinear,
            )

    # Read corresponding S1 valid mask window
    with rasterio.open(s1_valid_path) as s1_v_src:
        s1_valid_raw = s1_v_src.read(1, window=s1_window).astype(np.float32)
        s1_v_win_transform = s1_v_src.window_transform(s1_window)

        s1_valid_aligned = np.zeros((patch_size, patch_size), dtype=np.float32)
        reproject(
            source=s1_valid_raw,
            destination=s1_valid_aligned,
            src_transform=s1_v_win_transform,
            src_crs=s1_v_src.crs,
            dst_transform=s2_win_transform,
            dst_crs=s2_crs,
            resampling=Resampling.nearest,
        )

    return s1_aligned, s1_valid_aligned


def _apply_geometric_augmentation(
    s1: Tensor,
    s2: Tensor,
    mask: Tensor,
    valid: Tensor,
) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    """Apply synchronized spatial flips/rotations across all four tensors."""
    if random.random() < 0.5:
        s1 = torch.flip(s1, dims=[-1])
        s2 = torch.flip(s2, dims=[-1])
        mask = torch.flip(mask, dims=[-1])
        valid = torch.flip(valid, dims=[-1])
    if random.random() < 0.5:
        s1 = torch.flip(s1, dims=[-2])
        s2 = torch.flip(s2, dims=[-2])
        mask = torch.flip(mask, dims=[-2])
        valid = torch.flip(valid, dims=[-2])
    rotations = random.randint(0, 3)
    if rotations:
        s1 = torch.rot90(s1, rotations, dims=[-2, -1])
        s2 = torch.rot90(s2, rotations, dims=[-2, -1])
        mask = torch.rot90(mask, rotations, dims=[-2, -1])
        valid = torch.rot90(valid, rotations, dims=[-2, -1])
    return s1, s2, mask, valid


@dataclass(frozen=True)
class PatchIndex:
    scene: ScenePaths
    row_off: int
    col_off: int


class S1S2WaterDataset(Dataset[dict[str, Any]]):
    """Windowed S1S2-Water patch dataset with S1 resampled onto the S2 grid.

    Key Features:
      - Supports arbitrary, non-consecutive scene IDs (e.g. [1, 5, 6, 7, 8]).
      - Applies S1 storage scale (/100.0) and S2 scale (/10000.0).
      - Applies deterministic, reproducible normalization (no per-patch min-max).
      - Primary patch generation: deterministic regular grid tiling via `stride`.
      - Optional patch generation: random sampling via `patches_per_scene`.
      - Lazy windowed reading: no full scenes loaded into memory.
      - Effective valid mask: s2_valid & s1_valid_resampled.
    """

    def __init__(
        self,
        root_dir: str | Path,
        scene_ids: Sequence[int | str] | None = None,
        sample_ids: Sequence[int | str] | None = None,  # backwards compatibility alias
        patch_size: int = 256,
        stride: int | None = 256,
        patches_per_scene: int | None = None,
        split: str | None = None,
        augment: bool = False,
        normalization_config: NormalizationConfig | None = None,
        min_valid_ratio: float = 0.05,
        ignore_missing: bool = False,
        seed: int = 0,
        max_index_attempts: int = 200,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.patch_size = patch_size
        self.stride = stride
        self.patches_per_scene = patches_per_scene
        self.split = _normalize_split(split) if split is not None else None
        self.augment = augment and (self.split is None or self.split == "train")
        self.norm_config = normalization_config or DEFAULT_NORM_CONFIG
        self.min_valid_ratio = min_valid_ratio
        self.ignore_missing = ignore_missing
        self.rng = random.Random(seed)
        self.max_index_attempts = max_index_attempts

        # Resolve explicit scene IDs (scene_ids or legacy sample_ids)
        explicit_ids = scene_ids if scene_ids is not None else sample_ids
        if explicit_ids is not None:
            explicit_strs = [str(sid) for sid in explicit_ids]
            self.scenes = self._resolve_explicit_scenes(explicit_strs)
        else:
            discovered = discover_scene_ids(self.root_dir)
            if not discovered:
                raise ValueError(f"No S1S2-Water scenes found under {self.root_dir}")
            self.scenes = self._filter_discovered_scenes(discovered)

        if not self.scenes:
            raise ValueError(
                f"No valid scenes available under {self.root_dir} for split='{self.split}'"
            )

        self._patches = self._build_patch_index()
        if not self._patches:
            raise ValueError(
                f"No valid {patch_size}x{patch_size} patches found in {len(self.scenes)} scene(s)."
            )

    def _resolve_explicit_scenes(self, scene_ids: list[str]) -> list[ScenePaths]:
        scenes: list[ScenePaths] = []
        missing_scenes: list[str] = []

        for sid in scene_ids:
            paths = _scene_paths(self.root_dir, sid)
            required = (
                paths.s1_img,
                paths.s1_valid,
                paths.s2_img,
                paths.s2_msk,
                paths.s2_valid,
            )
            if not all(p.is_file() for p in required):
                missing_scenes.append(sid)
                continue

            # If user explicitly passed scene_ids AND also specified split, check meta split
            if self.split is not None:
                scene_split = _read_scene_split(paths.meta)
                if scene_split is not None and scene_split != self.split:
                    continue

            scenes.append(paths)

        if missing_scenes and not self.ignore_missing:
            raise FileNotFoundError(
                f"Requested scene(s) missing or incomplete: {missing_scenes} under {self.root_dir}"
            )

        return scenes

    def _filter_discovered_scenes(self, discovered_ids: list[str]) -> list[ScenePaths]:
        scenes: list[ScenePaths] = []
        for sid in discovered_ids:
            paths = _scene_paths(self.root_dir, sid)
            required = (
                paths.s1_img,
                paths.s1_valid,
                paths.s2_img,
                paths.s2_msk,
                paths.s2_valid,
            )
            if not all(p.is_file() for p in required):
                continue
            if self.split is not None:
                scene_split = _read_scene_split(paths.meta)
                if scene_split is not None and scene_split != self.split:
                    continue
            scenes.append(paths)
        return scenes

    def _build_patch_index(self) -> list[PatchIndex]:
        """Index patches either deterministically by stride (default) or randomly."""
        patches: list[PatchIndex] = []

        for scene in self.scenes:
            with rasterio.open(scene.s2_img) as s2_src:
                height, width = s2_src.height, s2_src.width

            if height < self.patch_size or width < self.patch_size:
                continue

            max_row = height - self.patch_size
            max_col = width - self.patch_size

            # Deterministic grid tiling via stride
            if self.stride is not None and self.stride > 0:
                with rasterio.open(scene.s2_valid) as valid_src:
                    for row_off in range(0, max_row + 1, self.stride):
                        for col_off in range(0, max_col + 1, self.stride):
                            window = Window(col_off, row_off, self.patch_size, self.patch_size)
                            valid_patch = valid_src.read(1, window=window)
                            valid_ratio = np.count_nonzero(valid_patch) / float(self.patch_size * self.patch_size)
                            if valid_ratio >= self.min_valid_ratio:
                                patches.append(
                                    PatchIndex(scene=scene, row_off=row_off, col_off=col_off)
                                )
            # Random sampling per scene
            elif self.patches_per_scene is not None and self.patches_per_scene > 0:
                with rasterio.open(scene.s2_valid) as valid_src:
                    accepted = 0
                    attempts = 0
                    while accepted < self.patches_per_scene and attempts < self.max_index_attempts:
                        attempts += 1
                        row_off = self.rng.randint(0, max_row)
                        col_off = self.rng.randint(0, max_col)
                        window = Window(col_off, row_off, self.patch_size, self.patch_size)
                        valid_patch = valid_src.read(1, window=window)
                        valid_ratio = np.count_nonzero(valid_patch) / float(self.patch_size * self.patch_size)
                        if valid_ratio >= self.min_valid_ratio:
                            patches.append(
                                PatchIndex(scene=scene, row_off=row_off, col_off=col_off)
                            )
                            accepted += 1

        return patches

    def __len__(self) -> int:
        return len(self._patches)

    def _load_patch(self, patch: PatchIndex) -> dict[str, Any]:
        s2_window = Window(
            patch.col_off,
            patch.row_off,
            self.patch_size,
            self.patch_size,
        )

        # 1. Read S2 windowed bands and masks
        with rasterio.open(patch.scene.s2_img) as s2_src:
            s2_patch_raw = s2_src.read(window=s2_window).astype(np.float32)
            # 2. Windowed alignment of S1 to S2 patch grid
            s1_aligned_raw, s1_valid_aligned = align_windowed_s1_to_s2(
                s1_img_path=patch.scene.s1_img,
                s1_valid_path=patch.scene.s1_valid,
                s2_src=s2_src,
                s2_window=s2_window,
                patch_size=self.patch_size,
            )

        with rasterio.open(patch.scene.s2_msk) as msk_src:
            mask = msk_src.read(1, window=s2_window).astype(np.float32)

        with rasterio.open(patch.scene.s2_valid) as valid_src:
            valid_s2 = valid_src.read(1, window=s2_window).astype(np.float32)

        # 3. Apply documented S1S2-Water storage scale factors:
        #    S1 stored values / 100.0 (-> dB)
        #    S2 stored values / 10000.0 (-> reflectance)
        s1_db = s1_aligned_raw / S1_STORAGE_SCALE
        s2_refl = s2_patch_raw / S2_STORAGE_SCALE

        # 4. Apply deterministic, reproducible normalization
        s1_norm = normalize_s1(s1_db, self.norm_config)
        s2_norm = normalize_s2(s2_refl, self.norm_config)

        # 5. Effective valid mask: pixel must be valid in both S2 and resampled S1
        effective_valid = (valid_s2 > 0.5) & (s1_valid_aligned > 0.5)

        # 6. Convert to PyTorch float32 tensors
        s1_t = torch.from_numpy(s1_norm.astype(np.float32))
        s2_t = torch.from_numpy(s2_norm.astype(np.float32))
        mask_t = torch.from_numpy((mask > 0.5).astype(np.float32))
        valid_t = torch.from_numpy(effective_valid.astype(np.float32))

        # 7. Synchronized spatial augmentation (if enabled)
        if self.augment:
            s1_t, s2_t, mask_t, valid_t = _apply_geometric_augmentation(
                s1_t, s2_t, mask_t, valid_t
            )

        return {
            "s1": s1_t,
            "s2": s2_t,
            "mask": mask_t,
            "valid": valid_t,
            "sample_id": patch.scene.sample_id,
            "scene_id": patch.scene.sample_id,
            "row_off": patch.row_off,
            "col_off": patch.col_off,
        }

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._load_patch(self._patches[index])

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
import torch
from rasterio.transform import from_origin

from training.s1s2_water_dataset import (
    DEFAULT_NORM_CONFIG,
    NormalizationConfig,
    S1S2WaterDataset,
    discover_scene_ids,
    inspect_s1_mask,
    inspect_scene_availability,
    normalize_s1,
    normalize_s2,
)
from training.test_s1s2_dataset import save_visualization


def _write_geotiff(
    path: Path,
    array: np.ndarray,
    *,
    transform: rasterio.Affine,
    crs: str = "EPSG:32652",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if array.ndim == 2:
        count = 1
        data = array[np.newaxis, ...]
    else:
        count = array.shape[0]
        data = array
    profile = {
        "driver": "GTiff",
        "height": data.shape[1],
        "width": data.shape[2],
        "count": count,
        "dtype": data.dtype,
        "crs": crs,
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)


def _make_synthetic_scene(root: Path, sample_id: str = "1", split: str = "train") -> Path:
    scene_dir = root / sample_id
    s2_size = 512
    # S1 native resolution 9m vs S2 native resolution 10m
    s1_size = int(round(s2_size * 10 / 9))  # 569x569
    s2_transform = from_origin(500_000.0, 4_500_000.0, 10.0, 10.0)
    s1_transform = from_origin(500_000.0, 4_500_000.0, 9.0, 9.0)

    # Geometry: Circular water body
    yy, xx = np.mgrid[0:s2_size, 0:s2_size]
    water = ((xx - 200) ** 2 + (yy - 200) ** 2 < 60**2).astype(np.uint8)

    # S2 reflectance scaled by 10000 (uint16)
    # Background reflectance ~ 800-1200, water reflectance low in NIR/SWIR
    s2 = np.zeros((6, s2_size, s2_size), dtype=np.uint16)
    s2[0] = 800   # Blue
    s2[1] = 900   # Green
    s2[2] = 700   # Red
    s2[3] = 2500  # NIR
    s2[4] = 1800  # SWIR1
    s2[5] = 1200  # SWIR2
    # Water pixels: low NIR and SWIR
    s2[0, water > 0] = 600
    s2[1, water > 0] = 700
    s2[2, water > 0] = 400
    s2[3, water > 0] = 200
    s2[4, water > 0] = 100
    s2[5, water > 0] = 80

    # S1 SAR values stored as int16 scaled by 100 (e.g. -1500 = -15 dB)
    # Water has low backscatter (smooth surface, e.g. -24 dB = -2400)
    # Land has higher backscatter (rough surface, e.g. -12 dB = -1200)
    s1 = np.full((2, s1_size, s1_size), -1200, dtype=np.int16)
    # Map water approx to S1 grid
    yy_s1, xx_s1 = np.mgrid[0:s1_size, 0:s1_size]
    water_s1 = ((xx_s1 - int(200 * 10 / 9)) ** 2 + (yy_s1 - int(200 * 10 / 9)) ** 2 < int(60 * 10 / 9) ** 2)
    s1[0, water_s1] = -2400  # VV in water: -24 dB
    s1[1, water_s1] = -2900  # VH in water: -29 dB

    # Valid masks (1 = valid, 0 = invalid border)
    valid_s2 = np.ones((s2_size, s2_size), dtype=np.uint8)
    valid_s2[:4, :] = 0
    valid_s2[:, -4:] = 0

    valid_s1 = np.ones((s1_size, s1_size), dtype=np.uint8)
    valid_s1[-5:, :] = 0

    _write_geotiff(scene_dir / f"sentinel12_s2_{sample_id}_img.tif", s2, transform=s2_transform)
    _write_geotiff(scene_dir / f"sentinel12_s2_{sample_id}_msk.tif", water, transform=s2_transform)
    _write_geotiff(scene_dir / f"sentinel12_s2_{sample_id}_valid.tif", valid_s2, transform=s2_transform)
    _write_geotiff(scene_dir / f"sentinel12_s1_{sample_id}_img.tif", s1, transform=s1_transform)
    _write_geotiff(scene_dir / f"sentinel12_s1_{sample_id}_msk.tif", water_s1.astype(np.uint8), transform=s1_transform)
    _write_geotiff(scene_dir / f"sentinel12_s1_{sample_id}_valid.tif", valid_s1, transform=s1_transform)

    meta = {
        "properties": {
            "split": split,
            "scene_id": sample_id,
        }
    }
    (scene_dir / f"sentinel12_{sample_id}_meta.json").write_text(
        json.dumps(meta),
        encoding="utf-8",
    )
    return scene_dir


@pytest.fixture()
def multi_scene_root(tmp_path: Path) -> Path:
    # Create non-consecutive scene IDs: 1, 5, 6, 7, 8 (omitting 2, 3, 4)
    _make_synthetic_scene(tmp_path, "1", split="train")
    _make_synthetic_scene(tmp_path, "5", split="train")
    _make_synthetic_scene(tmp_path, "6", split="train")
    _make_synthetic_scene(tmp_path, "7", split="train")
    _make_synthetic_scene(tmp_path, "8", split="val")
    return tmp_path


def test_non_consecutive_scene_discovery(multi_scene_root: Path) -> None:
    discovered = discover_scene_ids(multi_scene_root)
    # Must find 1, 5, 6, 7, 8 in natural numerical order
    assert discovered == ["1", "5", "6", "7", "8"]

    # Check availability report
    avail = inspect_scene_availability(multi_scene_root, [1, 5, 6, 7, 8, 99])
    assert avail["requested"] == ["1", "5", "6", "7", "8", "99"]
    assert avail["available"] == ["1", "5", "6", "7", "8"]
    assert avail["missing"] == ["99"]


def test_missing_files_detection(tmp_path: Path) -> None:
    scene_dir = tmp_path / "1"
    scene_dir.mkdir(parents=True)
    # Only create s2_img, omit required s1_img and others
    (scene_dir / "sentinel12_s2_1_img.tif").write_bytes(b"dummy")

    with pytest.raises(FileNotFoundError, match="missing or incomplete"):
        S1S2WaterDataset(root_dir=tmp_path, scene_ids=[1], ignore_missing=False)

    # With ignore_missing=True, should raise ValueError that no scenes are available
    with pytest.raises(ValueError, match="No valid scenes"):
        S1S2WaterDataset(root_dir=tmp_path, scene_ids=[1], ignore_missing=True)


def test_s1s2_water_dataset_shapes_and_alignment(multi_scene_root: Path) -> None:
    # Test deterministic stride tiling
    dataset = S1S2WaterDataset(
        root_dir=multi_scene_root,
        scene_ids=[1, 5],
        patch_size=256,
        stride=256,
        augment=False,
    )
    assert len(dataset) > 0

    sample = dataset[0]
    # S1 shape: [2, 256, 256]
    assert sample["s1"].shape == (2, 256, 256)
    # S2 shape: [6, 256, 256]
    assert sample["s2"].shape == (6, 256, 256)
    # Mask shape: [256, 256]
    assert sample["mask"].shape == (256, 256)
    # Valid shape: [256, 256]
    assert sample["valid"].shape == (256, 256)

    assert sample["s1"].dtype == torch.float32
    assert sample["s2"].dtype == torch.float32
    assert sample["mask"].dtype == torch.float32
    assert sample["valid"].dtype == torch.float32


def test_numeric_checks_no_nan_no_inf(multi_scene_root: Path) -> None:
    dataset = S1S2WaterDataset(
        root_dir=multi_scene_root,
        scene_ids=[1],
        patch_size=256,
        stride=256,
    )
    sample = dataset[0]
    s1, s2 = sample["s1"], sample["s2"]

    assert not torch.isnan(s1).any()
    assert not torch.isnan(s2).any()
    assert not torch.isinf(s1).any()
    assert not torch.isinf(s2).any()
    assert torch.isfinite(s1).all()
    assert torch.isfinite(s2).all()


def test_mask_and_valid_mask_values(multi_scene_root: Path) -> None:
    dataset = S1S2WaterDataset(
        root_dir=multi_scene_root,
        scene_ids=[1],
        patch_size=256,
        stride=256,
    )
    sample = dataset[0]
    mask = sample["mask"]
    valid = sample["valid"]

    # Verify mask is strictly binary
    unique_mask = set(torch.unique(mask).tolist())
    assert unique_mask.issubset({0.0, 1.0})

    # Verify valid mask is strictly binary
    unique_valid = set(torch.unique(valid).tolist())
    assert unique_valid.issubset({0.0, 1.0})
    assert (valid > 0.5).sum().item() > 0


def test_storage_scale_factors_and_deterministic_normalization() -> None:
    # Test S1 scale factor / 100.0
    raw_s1 = np.array([[-1500.0, -2500.0]], dtype=np.float32)  # int16 scaled
    scaled_s1 = raw_s1 / 100.0  # [-15.0, -25.0] dB
    assert np.allclose(scaled_s1, [[-15.0, -25.0]])

    # Test S2 scale factor / 10000.0
    raw_s2 = np.array([[800.0, 2500.0]], dtype=np.float32)  # uint16 scaled
    scaled_s2 = raw_s2 / 10000.0  # [0.08, 0.25]
    assert np.allclose(scaled_s2, [[0.08, 0.25]])

    # Test deterministic minmax normalization
    config = NormalizationConfig(mode="minmax")
    # VV min=-30, max=0; -15 dB maps to (-15 - (-30))/(0 - (-30)) = 15/30 = 0.5
    s1_in = np.array([[[-15.0]], [[-20.0]]], dtype=np.float32)
    s1_norm = normalize_s1(s1_in, config)
    assert np.isclose(s1_norm[0, 0, 0], 0.5)

    # Determinism: same input always produces exact same output (no per-patch quantile drift)
    s1_norm_2 = normalize_s1(s1_in, config)
    assert np.all(s1_norm == s1_norm_2)


def test_scene_level_split(multi_scene_root: Path) -> None:
    # Scene 1, 5, 6, 7 are train, scene 8 is val
    train_ds = S1S2WaterDataset(
        root_dir=multi_scene_root,
        scene_ids=[1, 5, 6, 7],
        patch_size=256,
        stride=256,
    )
    val_ds = S1S2WaterDataset(
        root_dir=multi_scene_root,
        scene_ids=[8],
        patch_size=256,
        stride=256,
    )

    train_scenes = {p.scene.sample_id for p in train_ds._patches}
    val_scenes = {p.scene.sample_id for p in val_ds._patches}

    assert train_scenes == {"1", "5", "6", "7"}
    assert val_scenes == {"8"}
    # No scene overlap between train and val
    assert len(train_scenes.intersection(val_scenes)) == 0


def test_s1_mask_inspection(multi_scene_root: Path) -> None:
    s1_msk_path = multi_scene_root / "1" / "sentinel12_s1_1_msk.tif"
    info = inspect_s1_mask(s1_msk_path)
    assert info["exists"] is True
    assert "EPSG:32652" in info["crs"]
    assert info["res"] == (9.0, 9.0)
    assert set(info["unique_values"]).issubset({0, 1})


def test_patch_visualization_output(multi_scene_root: Path, tmp_path: Path) -> None:
    dataset = S1S2WaterDataset(
        root_dir=multi_scene_root,
        scene_ids=[1],
        patch_size=256,
        stride=256,
    )
    sample = dataset[0]
    out_png = tmp_path / "test_vis.png"
    save_visualization(sample, out_png)
    assert out_png.is_file()
    assert out_png.stat().st_size > 1000

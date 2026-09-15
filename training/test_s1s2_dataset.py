from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import torch

from training.s1s2_water_dataset import (
    DEFAULT_NORM_CONFIG,
    NormalizationConfig,
    S1S2WaterDataset,
    discover_scene_ids,
    inspect_s1_mask,
    inspect_scene_availability,
)


def _inspect_scene_geospatial(scene_dir: Path, scene_id: str) -> dict[str, Any]:
    """Inspect native CRS, resolution, and dimensions for S1 and S2."""
    s1_path = scene_dir / f"sentinel12_s1_{scene_id}_img.tif"
    s2_path = scene_dir / f"sentinel12_s2_{scene_id}_img.tif"
    s1_msk_path = scene_dir / f"sentinel12_s1_{scene_id}_msk.tif"
    s2_msk_path = scene_dir / f"sentinel12_s2_{scene_id}_msk.tif"

    info: dict[str, Any] = {}

    if s1_path.is_file():
        with rasterio.open(s1_path) as s1:
            info["s1"] = {
                "crs": str(s1.crs),
                "resolution": s1.res,
                "shape": (s1.height, s1.width),
                "count": s1.count,
                "dtypes": s1.dtypes,
            }

    if s2_path.is_file():
        with rasterio.open(s2_path) as s2:
            info["s2"] = {
                "crs": str(s2.crs),
                "resolution": s2.res,
                "shape": (s2.height, s2.width),
                "count": s2.count,
                "dtypes": s2.dtypes,
            }

    # Inspect S1 mask vs S2 mask
    info["s1_msk"] = inspect_s1_mask(s1_msk_path)
    if s2_msk_path.is_file():
        with rasterio.open(s2_msk_path) as s2_m:
            m_data = s2_m.read(1)
            info["s2_msk"] = {
                "exists": True,
                "crs": str(s2_m.crs),
                "resolution": s2_m.res,
                "shape": (s2_m.height, s2_m.width),
                "unique_values": np.unique(m_data).tolist(),
                "non_zero_count": int(np.count_nonzero(m_data)),
            }
    else:
        info["s2_msk"] = {"exists": False}

    return info


def save_visualization(sample: dict[str, Any], output_path: Path) -> None:
    """Produce 5-panel visualization:
    1. S2 RGB (B04 Red, B03 Green, B02 Blue)
    2. S1 VV (SAR channel 0)
    3. Water mask (ground truth binary)
    4. S2 RGB + Water mask overlay
    5. Aligned S1 VV + S2 False-Color composite
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not available; skipping visualization image saving.")
        return

    s1 = sample["s1"].numpy()  # [2, H, W]
    s2 = sample["s2"].numpy()  # [6, H, W] (Blue=0, Green=1, Red=2, NIR=3, SWIR1=4, SWIR2=5)
    mask = sample["mask"].numpy()  # [H, W]
    valid = sample["valid"].numpy()  # [H, W]

    # Create S2 RGB from channels: Red=2, Green=1, Blue=0
    # Normalize to [0, 1] for display
    rgb = np.stack([s2[2], s2[1], s2[0]], axis=-1)
    rgb = np.clip(rgb, 0.0, 1.0)

    # S1 VV SAR
    vv = s1[0]
    vv_disp = np.clip(vv, 0.0, 1.0)

    # Overlay: S2 RGB with water mask in cyan
    overlay = rgb.copy()
    water_pixels = mask > 0.5
    overlay[water_pixels] = overlay[water_pixels] * 0.35 + np.array([0.0, 0.85, 1.0]) * 0.65

    # Aligned Composite: Red=NIR (ch 3), Green=VV (S1 ch 0), Blue=Green (S2 ch 1)
    nir = np.clip(s2[3], 0.0, 1.0)
    composite = np.stack([nir, vv_disp, np.clip(s2[1], 0.0, 1.0)], axis=-1)

    fig, axes = plt.subplots(1, 5, figsize=(20, 4.2))

    axes[0].imshow(rgb)
    axes[0].set_title("S2 True Color (RGB)", fontsize=11)
    axes[0].axis("off")

    im1 = axes[1].imshow(vv_disp, cmap="bone")
    axes[1].set_title("Aligned S1 VV (SAR)", fontsize=11)
    axes[1].axis("off")
    plt.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)

    im2 = axes[2].imshow(mask, cmap="Blues", vmin=0, vmax=1)
    axes[2].set_title("Water Mask (Target)", fontsize=11)
    axes[2].axis("off")
    plt.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)

    axes[3].imshow(overlay)
    axes[3].set_title("S2 + Water Mask Overlay", fontsize=11)
    axes[3].axis("off")

    axes[4].imshow(composite)
    axes[4].set_title("Aligned S1/S2 Composite\n(NIR, VV, Green)", fontsize=10)
    axes[4].axis("off")

    scene_id = sample.get("scene_id", sample.get("sample_id", "unknown"))
    row_off = sample.get("row_off", 0)
    col_off = sample.get("col_off", 0)
    plt.suptitle(
        f"S1S2-Water Aligned Patch â€” Scene {scene_id} [Origin: ({row_off}, {col_off})]",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved patch visualization to {output_path}")


def _summarize_sample(sample: dict[str, Any], index: int) -> None:
    s1 = sample["s1"]
    s2 = sample["s2"]
    mask = sample["mask"]
    valid = sample["valid"]

    water_pixels = int((mask > 0.5).sum().item())
    total_pixels = mask.numel()
    valid_pixels = int((valid > 0.5).sum().item())

    has_nan_s1 = torch.isnan(s1).any().item()
    has_nan_s2 = torch.isnan(s2).any().item()
    has_inf_s1 = torch.isinf(s1).any().item()
    has_inf_s2 = torch.isinf(s2).any().item()

    print(f"\n--- Sample Patch #{index} ---")
    print(f"Scene ID:    {sample.get('scene_id', sample.get('sample_id'))}")
    print(f"Patch Origin: (row={sample.get('row_off')}, col={sample.get('col_off')})")
    print(f"S1 Tensor:   shape={tuple(s1.shape)} dtype={s1.dtype} range=[{s1.min().item():.4f}, {s1.max().item():.4f}]")
    print(f"S2 Tensor:   shape={tuple(s2.shape)} dtype={s2.dtype} range=[{s2.min().item():.4f}, {s2.max().item():.4f}]")
    print(f"Mask:        shape={tuple(mask.shape)} dtype={mask.dtype} unique={torch.unique(mask).tolist()}")
    print(f"Valid:       shape={tuple(valid.shape)} dtype={valid.dtype} unique={torch.unique(valid).tolist()}")
    print(f"Water Pixels: {water_pixels}/{total_pixels} ({water_pixels/total_pixels*100:.2f}%)")
    print(f"Valid Pixels: {valid_pixels}/{total_pixels} ({valid_pixels/total_pixels*100:.2f}%)")
    print(f"Numeric OK:  No NaN: {not (has_nan_s1 or has_nan_s2)} | No Inf: {not (has_inf_s1 or has_inf_s2)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test S1S2-Water dataset loader and geospatial alignment.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("S1S2_WATER_ROOT", "/content/S1S2-Water")),
        help="Path to S1S2-Water dataset root",
    )
    parser.add_argument(
        "--scene-ids",
        nargs="+",
        default=["1", "5", "6", "7", "8"],
        help="List of scene IDs to test (e.g. 1 5 6 7 8)",
    )
    parser.add_argument("--patch-size", default=256, type=int, help="Patch size (pixels)")
    parser.add_argument("--stride", default=256, type=int, help="Deterministic stride (pixels)")
    parser.add_argument("--patches-per-scene", default=None, type=int, help="Optional random patches per scene")
    parser.add_argument("--split", default=None, type=str, help="Split filter (e.g. train, val, or None)")
    parser.add_argument("--samples", default=3, type=int, help="Number of sample patches to summarize")
    parser.add_argument("--ignore-missing", action="store_true", help="Do not raise error if some requested scenes are missing")
    parser.add_argument(
        "--visualize",
        type=Path,
        default=Path("training/s1s2_water_visualization.png"),
        help="Path to save visualization figure",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("S1S2-Water Real Sentinel-1 + Sentinel-2 Dataset Validation")
    print("=" * 70)
    print(f"Dataset root: {args.data}")

    if not args.data.is_dir():
        print(f"\n[INFO] Dataset root does not exist on this machine: {args.data}")
        print("This is expected when running in a local IDE prior to Google Colab execution.")
        print("To run against synthetic data or verify unit tests, execute pytest:")
        print("  python -m pytest training/tests/test_s1s2_water_dataset.py -v")
        return

    # 1. Inspect dynamic discovery
    discovered_all = discover_scene_ids(args.data)
    print(f"\n[Discovery] Found {len(discovered_all)} total scene directory/directories on disk:")
    print(f"  Discovered IDs: {discovered_all}")

    # 2. Check scene availability for requested IDs
    avail = inspect_scene_availability(args.data, args.scene_ids)
    print(f"\n[Scene Availability Check]")
    print(f"  Requested Scene IDs:  {avail['requested']}")
    print(f"  Available Scene IDs:  {avail['available']}")
    print(f"  Missing Scene IDs:    {avail['missing']}")

    if not avail["available"]:
        print("\n[ERROR] None of the requested scenes are fully available.")
        return

    # 3. Geospatial inspection of the first available scene
    first_id = avail["available"][0]
    scene_dir = args.data / first_id
    geo_info = _inspect_scene_geospatial(scene_dir, first_id)
    print(f"\n[Geospatial Inspection: Scene {first_id}]")
    if "s1" in geo_info:
        s1_info = geo_info["s1"]
        print(f"  S1 CRS:        {s1_info['crs']}")
        print(f"  S1 Resolution: {s1_info['resolution']}")
        print(f"  S1 Dimensions: {s1_info['shape']} (bands={s1_info['count']}, dtypes={s1_info['dtypes']})")
    if "s2" in geo_info:
        s2_info = geo_info["s2"]
        print(f"  S2 CRS:        {s2_info['crs']}")
        print(f"  S2 Resolution: {s2_info['resolution']}")
        print(f"  S2 Dimensions: {s2_info['shape']} (bands={s2_info['count']}, dtypes={s2_info['dtypes']})")

    if "s1_msk" in geo_info:
        s1m = geo_info["s1_msk"]
        print(f"  S1 Mask (*_msk.tif): exists={s1m.get('exists')}, unique_vals={s1m.get('unique_values')}, non_zero={s1m.get('non_zero_count')}")
    if "s2_msk" in geo_info:
        s2m = geo_info["s2_msk"]
        print(f"  S2 Mask (*_msk.tif): exists={s2m.get('exists')}, unique_vals={s2m.get('unique_values')}, non_zero={s2m.get('non_zero_count')}")

    # 4. Instantiate dataset loader
    use_scenes = avail["available"] if args.ignore_missing else [sid for sid in args.scene_ids if sid in avail["available"]]
    dataset = S1S2WaterDataset(
        root_dir=args.data,
        scene_ids=use_scenes,
        patch_size=args.patch_size,
        stride=args.stride if args.patches_per_scene is None else None,
        patches_per_scene=args.patches_per_scene,
        split=args.split,
        augment=False,
        normalization_config=DEFAULT_NORM_CONFIG,
        ignore_missing=args.ignore_missing,
    )

    print(f"\n[Dataset Initialized]")
    print(f"  Indexed patches:   {len(dataset)}")
    print(f"  Scenes used:       {[s.sample_id for s in dataset.scenes]}")
    print(f"  Patch size:        {args.patch_size}x{args.patch_size}")
    print(f"  Stride:            {args.stride}")
    print(f"  Normalization:     {DEFAULT_NORM_CONFIG.mode}")

    # 5. Summarize sample patches
    num_samples = min(args.samples, len(dataset))
    for i in range(num_samples):
        sample = dataset[i]
        _summarize_sample(sample, i)
        if i == 0 and args.visualize:
            save_visualization(sample, args.visualize)

    print("\n" + "=" * 70)
    print("S1S2-Water validation complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()

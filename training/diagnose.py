from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# Support both recommended module execution (`python -m training.diagnose`)
# and direct Colab file execution (`python training/diagnose.py`).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.evaluate import load_optical_sar_model
from training.fusion_model import OpticalSarFusionSegmenter
from training.losses import MaskedWaterLoss, metrics_from_counts
from training.s1s2_water_dataset import (
    DEFAULT_NORM_CONFIG,
    NormalizationConfig,
    S1S2WaterDataset,
)
from training.train import _collate_patches

THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def evaluate_probability_distribution(
    probs: torch.Tensor,
    valid_mask: torch.Tensor,
) -> dict[str, Any]:
    """Compute probability statistics exclusively on valid pixels."""
    valid_probs = probs[valid_mask].cpu().numpy()
    if len(valid_probs) == 0:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "threshold_percentages": {f"{t:.1f}": 0.0 for t in THRESHOLDS},
        }

    pcts = {}
    total_valid = float(len(valid_probs))
    for t in THRESHOLDS:
        cnt = np.count_nonzero(valid_probs > t)
        pcts[f"{t:.1f}"] = float(cnt / total_valid * 100.0)

    return {
        "min": float(np.min(valid_probs)),
        "max": float(np.max(valid_probs)),
        "mean": float(np.mean(valid_probs)),
        "median": float(np.median(valid_probs)),
        "threshold_percentages": pcts,
    }


def evaluate_threshold_sweep(
    probs: torch.Tensor,
    targets: torch.Tensor,
    valid_mask: torch.Tensor,
    smooth: float = 1e-6,
) -> dict[str, dict[str, float]]:
    """Compute Dice and IoU across a range of decision thresholds on valid pixels."""
    results = {}
    v_probs = probs[valid_mask]
    v_targets = (targets[valid_mask] > 0.5).float()

    for t in THRESHOLDS:
        preds = (v_probs > t).float()
        tp = int((preds * v_targets).sum().item())
        preds_sum = int(preds.sum().item())
        targets_sum = int(v_targets.sum().item())
        counts = {"tp": tp, "fp": preds_sum - tp, "fn": targets_sum - tp,
                  "tn": int(len(v_probs)) - preds_sum - targets_sum + tp,
                  "valid_pixels": int(len(v_probs))}
        metrics = metrics_from_counts(counts, smooth)

        results[f"{t:.1f}"] = {
            "dice": metrics["dice"],
            "iou": metrics["iou"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "water_pred_pct": float(preds_sum / max(1.0, float(len(v_probs))) * 100.0),
        }

    return results


def scene_water_statistics(dataset: S1S2WaterDataset) -> dict[str, Any]:
    """Summarize valid/water pixels and per-patch water ratios for one scene."""
    valid_pixels = water_pixels = empty_patches = 0
    ratios: list[float] = []
    for index in range(len(dataset)):
        sample = dataset[index]
        valid = sample["valid"] > 0.5
        water = (sample["mask"] > 0.5) & valid
        count = int(valid.sum().item())
        water_count = int(water.sum().item())
        valid_pixels += count
        water_pixels += water_count
        ratio = water_count / count if count else 0.0
        ratios.append(ratio)
        empty_patches += int(water_count == 0)
    return {
        "patch_count": len(dataset), "valid_pixel_count": valid_pixels,
        "water_pixel_count": water_pixels,
        "water_percentage": 100.0 * water_pixels / valid_pixels if valid_pixels else 0.0,
        "patch_water_ratio": {
            "min": float(np.min(ratios)) if ratios else 0.0,
            "median": float(np.median(ratios)) if ratios else 0.0,
            "mean": float(np.mean(ratios)) if ratios else 0.0,
            "max": float(np.max(ratios)) if ratios else 0.0,
            "empty_water_patches": empty_patches,
        },
    }


def run_scene_diagnostic(
    model: OpticalSarFusionSegmenter,
    dataset: S1S2WaterDataset,
    batch_size: int = 8,
    device: torch.device | None = None,
    max_patches: int | None = None,
) -> dict[str, Any]:
    """Evaluate checkpoint on a single scene, logging loss, metrics, and prob stats."""
    dev = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.eval()
    model.to(dev)

    patches_to_eval = range(min(max_patches, len(dataset))) if max_patches else range(len(dataset))
    loader = DataLoader(
        torch.utils.data.Subset(dataset, patches_to_eval),
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=_collate_patches,
    )

    criterion = MaskedWaterLoss(bce_weight=1.0, dice_weight=1.0, batch_dice=True)

    all_probs = []
    all_targets = []
    all_valids = []
    total_loss = 0.0
    num_batches = 0

    with torch.no_grad():
        for batch in loader:
            s1 = batch["s1"].to(dev)
            s2 = batch["s2"].to(dev)
            mask = batch["mask"].to(dev)
            valid = batch["valid"].to(dev)

            logits = model(s1, s2)
            loss, _ = criterion(logits, mask, valid)
            probs = torch.sigmoid(logits)

            total_loss += loss.item()
            num_batches += 1

            all_probs.append(probs.cpu())
            all_targets.append(mask.cpu())
            all_valids.append(valid.cpu())

    if num_batches == 0:
        return {}

    full_probs = torch.cat(all_probs, dim=0)
    full_targets = torch.cat(all_targets, dim=0)
    full_valids = torch.cat(all_valids, dim=0)
    valid_mask = full_valids > 0.5

    avg_loss = total_loss / num_batches
    prob_stats = evaluate_probability_distribution(full_probs, valid_mask)
    sweep = evaluate_threshold_sweep(full_probs, full_targets, valid_mask)

    # Standard metrics at default 0.5 threshold
    std_metrics = sweep.get("0.5", {"dice": 0.0, "iou": 0.0})

    return {
        "num_patches": len(patches_to_eval),
        "loss": float(avg_loss),
        "dice_0.5": std_metrics["dice"],
        "iou_0.5": std_metrics["iou"],
        "probability_stats": prob_stats,
        "threshold_sweep": sweep,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run diagnostic evaluation of optical+SAR water checkpoint.")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("checkpoints/optical_sar_water.pt"),
        help="Path to optical_sar_water.pt checkpoint",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("S1S2_WATER_ROOT", "/content/S1S2-Water")),
        help="Path to S1S2-Water dataset root",
    )
    parser.add_argument("--scenes", nargs="+", default=["1", "5", "6", "7", "8"])
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-patches-per-scene", type=int, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().with_name("diagnostic_results.json"),
        help="JSON output path (default: alongside this script).",
    )
    args = parser.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 75)
    print("Optical+SAR Water Segmentation Diagnostic Report")
    print("=" * 75)
    print(f"Checkpoint: {args.checkpoint}")
    print(f"Dataset root: {args.data}")
    print(f"Device: {dev}")

    if not args.checkpoint.is_file():
        print(f"[ERROR] Checkpoint not found at {args.checkpoint}")
        return

    model, ckpt = load_optical_sar_model(args.checkpoint, dev)
    print(f"Model loaded successfully. Train scenes in ckpt: {ckpt.get('train_scenes')}, Val: {ckpt.get('val_scenes')}")

    if not args.data.is_dir():
        print(f"[INFO] Real dataset root {args.data} not available on this path.")
        return

    results = {}
    for sid in args.scenes:
        scene_dir = args.data / sid
        if not scene_dir.is_dir():
            print(f"[WARN] Scene {sid} not found under {args.data}; skipping.")
            continue

        ds = S1S2WaterDataset(
            root_dir=args.data,
            scene_ids=[sid],
            patch_size=256,
            stride=256,
            augment=False,
            normalization_config=DEFAULT_NORM_CONFIG,
            ignore_missing=True,
        )
        print(f"\n--- Evaluating Scene {sid} ({len(ds)} patches) ---")
        water_stats = scene_water_statistics(ds)
        print(f"  Valid pixels: {water_stats['valid_pixel_count']:,} | Water: {water_stats['water_pixel_count']:,} ({water_stats['water_percentage']:.3f}%)")
        diag = run_scene_diagnostic(
            model=model,
            dataset=ds,
            batch_size=args.batch_size,
            device=dev,
            max_patches=args.max_patches_per_scene,
        )
        results[sid] = {"water_statistics": water_stats, "evaluation": diag}
        print(f"  Loss:     {diag['loss']:.4f}")
        print(f"  Dice@0.5: {diag['dice_0.5']:.4f}")
        print(f"  IoU@0.5:  {diag['iou_0.5']:.4f}")
        if sid == "8":
            print("\n  Scene 8 Probability Distribution:")
            p_stats = diag["probability_stats"]
            print(f"    Min: {p_stats['min']:.4f} | Max: {p_stats['max']:.4f} | Mean: {p_stats['mean']:.4f} | Median: {p_stats['median']:.4f}")
            print("    % Pixels Above Threshold:")
            for t, pct in p_stats["threshold_percentages"].items():
                print(f"      > {t}: {pct:.2f}%")
            print("\n  Scene 8 Threshold Sweep:")
            for t, sw in diag["threshold_sweep"].items():
                print(f"      Thresh {t}: Dice={sw['dice']:.4f}, IoU={sw['iou']:.4f}, Precision={sw['precision']:.4f}, Recall={sw['recall']:.4f} (Water Pred: {sw['water_pred_pct']:.2f}%)")

    # Output JSON summary
    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved full diagnostic report to {out_path}")


if __name__ == "__main__":
    main()

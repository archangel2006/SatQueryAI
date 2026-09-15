from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from training.fusion_model import OpticalSarFusionSegmenter
from training.losses import MaskedWaterLoss, compute_masked_metrics, metrics_from_counts
from training.s1s2_water_dataset import (
    DEFAULT_NORM_CONFIG,
    NormalizationConfig,
    S1S2WaterDataset,
)
from training.train import _collate_patches


def load_optical_sar_model(
    checkpoint_path: str | Path,
    device: torch.device | None = None,
) -> tuple[OpticalSarFusionSegmenter, dict[str, Any]]:
    """Load OpticalSarFusionSegmenter and metadata from saved checkpoint."""
    dev = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(checkpoint_path, map_location=dev)

    model = OpticalSarFusionSegmenter(**ckpt.get("model_config", {
        "s1_channels": 2, "s2_channels": 6, "base_channels": 32,
    }))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(dev)
    model.eval()

    return model, ckpt


def evaluate_dataset(
    model: OpticalSarFusionSegmenter,
    dataset: S1S2WaterDataset,
    batch_size: int = 8,
    device: torch.device | None = None,
) -> dict[str, float]:
    """Run full evaluation on a dataset, computing average loss, Dice, and IoU."""
    dev = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.eval()
    model.to(dev)

    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=_collate_patches,
    )
    criterion = MaskedWaterLoss(bce_weight=1.0, dice_weight=1.0, batch_dice=True)

    total_loss = 0.0
    total_counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "valid_pixels": 0}
    num_batches = 0

    with torch.no_grad():
        for batch in loader:
            s1 = batch["s1"].to(dev)
            s2 = batch["s2"].to(dev)
            mask = batch["mask"].to(dev)
            valid = batch["valid"].to(dev)

            logits = model(s1, s2)
            loss, _ = criterion(logits, mask, valid)
            metrics = compute_masked_metrics(logits, mask, valid)

            total_loss += loss.item()
            for key in total_counts:
                total_counts[key] += int(metrics[key])
            num_batches += 1

    if num_batches == 0:
        return {"loss": 0.0, "dice": 0.0, "iou": 0.0}

    aggregate = metrics_from_counts(total_counts)
    return {
        "loss": total_loss / num_batches,
        "dice": aggregate["dice"],
        "iou": aggregate["iou"],
        "precision": aggregate["precision"],
        "recall": aggregate["recall"],
        **total_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Optical+SAR water segmentation checkpoint.")
    parser.add_argument("--checkpoint", required=True, type=Path, help="Path to checkpoint .pt file")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("S1S2_WATER_ROOT", "/content/S1S2-Water")),
        help="Path to S1S2-Water dataset root",
    )
    parser.add_argument("--val-scenes", nargs="+", default=None, help="Scenes to evaluate")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--patch-size", type=int, default=256)
    parser.add_argument("--stride", type=int, default=256)
    args = parser.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, ckpt = load_optical_sar_model(args.checkpoint, dev)
    val_scenes = args.val_scenes or ckpt.get("val_scenes", ["8"])
    norm_cfg = NormalizationConfig.from_dict(ckpt.get("normalization_config", {}))

    print(f"Evaluating checkpoint: {args.checkpoint}")
    print(f"Validation scenes:    {val_scenes}")

    dataset = S1S2WaterDataset(
        root_dir=args.data,
        scene_ids=val_scenes,
        patch_size=args.patch_size,
        stride=args.stride,
        augment=False,
        normalization_config=norm_cfg,
    )

    results = evaluate_dataset(model, dataset, batch_size=args.batch_size, device=dev)
    print(f"Evaluation Results (N={len(dataset)} patches):")
    print(f"  Loss: {results['loss']:.4f}")
    print(f"  Dice: {results['dice']:.4f}")
    print(f"  IoU:  {results['iou']:.4f}")


if __name__ == "__main__":
    main()

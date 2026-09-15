from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Subset

# Allow direct Colab execution: `python training/train.py ...`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.fusion_model import OpticalSarFusionSegmenter
from training.losses import MaskedWaterLoss, compute_masked_metrics, metrics_from_counts
from training.s1s2_water_dataset import (
    DEFAULT_NORM_CONFIG,
    NormalizationConfig,
    S1S2WaterDataset,
    discover_scene_ids,
    inspect_scene_availability,
)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def inspect_scene_metadata_split(scene_dir: Path, scene_id: str) -> str | None:
    """Read split defined in sentinel12_<id>_meta.json if present."""
    meta_path = scene_dir / f"sentinel12_{scene_id}_meta.json"
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        split = data.get("properties", {}).get("split")
        if split is None:
            split = data.get("split")
        if split is not None:
            s = str(split).strip().lower()
            return "val" if s in ("val", "validation") else s
        return None
    except Exception:
        return None


def resolve_scene_level_splits(
    root_dir: Path,
    scene_ids: list[str],
    explicit_train: list[str] | None = None,
    explicit_val: list[str] | None = None,
) -> tuple[list[str], list[str], str]:
    """Determine scene-level train and validation splits without spatial leakage.

    1. If explicit_train and explicit_val are passed, use them.
    2. Otherwise, check each scene's metadata JSON for a predefined split.
    3. If metadata does not distinguish train vs val, use documented 5-scene fallback:
       Train: ['1', '5', '6', '7'], Val: ['8'].
    """
    if explicit_train is not None and explicit_val is not None:
        train_scenes = [str(s) for s in explicit_train]
        val_scenes = [str(s) for s in explicit_val]
        source = "explicit_cli_arguments"
    else:
        # Check metadata for each available scene
        meta_splits: dict[str, str | None] = {}
        for sid in scene_ids:
            scene_dir = root_dir / sid
            meta_splits[sid] = inspect_scene_metadata_split(scene_dir, sid)

        train_from_meta = [sid for sid, sp in meta_splits.items() if sp == "train"]
        val_from_meta = [sid for sid, sp in meta_splits.items() if sp in ("val", "test")]

        if train_from_meta and val_from_meta:
            train_scenes = train_from_meta
            val_scenes = val_from_meta
            source = "dataset_metadata_json"
        else:
            # Documented 5-scene fallback split: 1, 5, 6, 7 train, 8 validation
            train_scenes = [sid for sid in scene_ids if sid != "8"]
            val_scenes = [sid for sid in scene_ids if sid == "8"]
            # If scene 8 is not in the set, reserve the last scene as val
            if not val_scenes and len(scene_ids) > 1:
                val_scenes = [scene_ids[-1]]
                train_scenes = [s for s in scene_ids if s != val_scenes[0]]
            source = "documented_5_scene_fallback (Train: 1,5,6,7 | Val: 8)"

    # Validate zero spatial overlap
    overlap = set(train_scenes).intersection(set(val_scenes))
    if overlap:
        raise ValueError(f"Spatial leakage detected! Scenes present in both train and val: {overlap}")

    return train_scenes, val_scenes, source


def _collate_patches(batch: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
    s1 = torch.stack([b["s1"] for b in batch], dim=0)
    s2 = torch.stack([b["s2"] for b in batch], dim=0)
    mask = torch.stack([b["mask"] for b in batch], dim=0).unsqueeze(1)
    valid = torch.stack([b["valid"] for b in batch], dim=0).unsqueeze(1)
    return {"s1": s1, "s2": s2, "mask": mask, "valid": valid}


def run_epoch_detailed(
    model: nn.Module,
    loader: DataLoader,
    criterion: MaskedWaterLoss,
    device: torch.device,
    optimizer: optim.Optimizer | None = None,
) -> dict[str, float]:
    """Execute one epoch using one globally aggregated valid-pixel confusion matrix."""
    is_train = optimizer is not None
    model.train() if is_train else model.eval()

    total_loss = 0.0
    total_counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "valid_pixels": 0}
    probability_sum = 0.0
    probability_count = 0
    probability_min = float("inf")
    probability_max = float("-inf")
    num_batches = 0

    ctx = torch.enable_grad() if is_train else torch.no_grad()
    with ctx:
        for batch in loader:
            s1 = batch["s1"].to(device, non_blocking=True)
            s2 = batch["s2"].to(device, non_blocking=True)
            mask = batch["mask"].to(device, non_blocking=True)
            valid = batch["valid"].to(device, non_blocking=True)

            if is_train and optimizer is not None:
                optimizer.zero_grad(set_to_none=True)

            logits = model(s1, s2)
            loss, _ = criterion(logits, mask, valid)

            if is_train and optimizer is not None:
                loss.backward()
                optimizer.step()

            metrics = compute_masked_metrics(logits, mask, valid)

            total_loss += loss.item()
            for key in total_counts:
                total_counts[key] += int(metrics[key])
            with torch.no_grad():
                valid_probs = torch.sigmoid(logits)[valid > 0.5]
                if valid_probs.numel():
                    probability_sum += float(valid_probs.sum().item())
                    probability_count += int(valid_probs.numel())
                    probability_min = min(probability_min, float(valid_probs.min().item()))
                    probability_max = max(probability_max, float(valid_probs.max().item()))
            num_batches += 1

    if num_batches == 0:
        return {"loss": 0.0, "dice": 0.0, "iou": 0.0, "precision": 0.0, "recall": 0.0}

    aggregate = metrics_from_counts(total_counts)
    return {
        "loss": total_loss / num_batches,
        **aggregate,
        "probability_mean": probability_sum / probability_count if probability_count else 0.0,
        "probability_min": probability_min if probability_count else 0.0,
        "probability_max": probability_max if probability_count else 0.0,
    }


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: MaskedWaterLoss,
    device: torch.device,
    optimizer: optim.Optimizer | None = None,
) -> tuple[float, float, float]:
    """Compatibility wrapper returning loss, Dice, and IoU."""
    metrics = run_epoch_detailed(model, loader, criterion, device, optimizer)
    return metrics["loss"], metrics["dice"], metrics["iou"]


def train_s1s2_water(
    root_dir: str | Path,
    train_scenes: list[str],
    val_scenes: list[str],
    checkpoint_path: str | Path,
    epochs: int = 5,
    batch_size: int = 8,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    patch_size: int = 256,
    stride: int = 256,
    bce_weight: float = 1.0,
    dice_weight: float = 1.0,
    pos_weight: float = 1.0,
    max_train_patches: int | None = None,
    max_val_patches: int | None = None,
    seed: int = 42,
    device: str | None = None,
    ignore_missing: bool = False,
) -> dict[str, Any]:
    """Train OpticalSarFusionSegmenter on scene-level split and save best checkpoint."""
    _set_seed(seed)
    requested_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    dev = torch.device(requested_device)
    if dev.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA was requested but this PyTorch build has no available CUDA device. "
            "In Colab, select Runtime > Change runtime type > T4 GPU (or another GPU), "
            "then restart the runtime and verify `torch.cuda.is_available()` is True. "
            "Use --device cpu only for a slow smoke test."
        )
    ckpt_path = Path(checkpoint_path)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("S1S2-Water Optical+SAR Segmentation Training")
    print("=" * 75)
    print(f"Device:           {dev}")
    print(f"Dataset root:     {root_dir}")
    print(f"Train scenes:     {train_scenes}")
    print(f"Val scenes:       {val_scenes}")
    print(f"Epochs:           {epochs} | Batch size: {batch_size} | Learning rate: {lr}")
    print(f"Patch size:       {patch_size}x{patch_size} | Stride: {stride}")

    # 1. Instantiate datasets (with scene-level split)
    train_ds = S1S2WaterDataset(
        root_dir=root_dir,
        scene_ids=train_scenes,
        patch_size=patch_size,
        stride=stride,
        augment=True,
        normalization_config=DEFAULT_NORM_CONFIG,
        ignore_missing=ignore_missing,
    )

    val_ds = S1S2WaterDataset(
        root_dir=root_dir,
        scene_ids=val_scenes,
        patch_size=patch_size,
        stride=stride,
        augment=False,
        normalization_config=DEFAULT_NORM_CONFIG,
        ignore_missing=ignore_missing,
    )

    train_data = Subset(train_ds, range(min(max_train_patches, len(train_ds)))) if max_train_patches else train_ds
    val_data = Subset(val_ds, range(min(max_val_patches, len(val_ds)))) if max_val_patches else val_ds

    train_loader = DataLoader(
        train_data,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=_collate_patches,
        pin_memory=(dev.type == "cuda"),
    )
    val_loader = DataLoader(
        val_data,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=_collate_patches,
        pin_memory=(dev.type == "cuda"),
    )

    print(f"\n[Data Loaders]")
    print(f"  Train patches:    {len(train_data):,} (from {len(train_scenes)} scenes)")
    print(f"  Val patches:      {len(val_data):,} (from {len(val_scenes)} scenes)")

    # 2. Instantiate model and loss
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=32).to(dev)
    print(f"  Model Parameters: {model.num_parameters:,}")

    criterion = MaskedWaterLoss(
        bce_weight=bce_weight, dice_weight=dice_weight,
        pos_weight=pos_weight, batch_dice=True,
    )
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)

    best_val_dice = 0.0
    best_val_iou = 0.0
    best_epoch = 0
    history: list[dict[str, Any]] = []

    print("\n" + "=" * 75)
    print(f"{'Epoch':>5} | {'Train Loss':>10} | {'Val Loss':>10} | {'Train Dice':>10} | {'Val Dice':>10} | {'Train IoU':>10} | {'Val IoU':>10} | {'Val Prec':>9} | {'Val Rec':>8} | {'Best':>5}")
    print("-" * 75)

    for epoch in range(1, epochs + 1):
        train_metrics = run_epoch_detailed(model, train_loader, criterion, dev, optimizer)
        val_metrics = run_epoch_detailed(model, val_loader, criterion, dev, None)
        tr_loss, tr_dice, tr_iou = train_metrics["loss"], train_metrics["dice"], train_metrics["iou"]
        va_loss, va_dice, va_iou = val_metrics["loss"], val_metrics["dice"], val_metrics["iou"]
        scheduler.step()

        is_best = va_dice > best_val_dice or (va_dice == best_val_dice and va_iou > best_val_iou)
        if is_best:
            best_val_dice = va_dice
            best_val_iou = va_iou
            best_epoch = epoch
            # Write-then-replace prevents a partial checkpoint from replacing a usable one.
            payload = {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "epoch": epoch,
                    "best_val_dice": best_val_dice,
                    "best_val_iou": best_val_iou,
                    "normalization_config": DEFAULT_NORM_CONFIG.to_dict(),
                    "model_config": {"s1_channels": 2, "s2_channels": 6, "base_channels": 32},
                    "training_config": {
                        "epochs": epochs, "batch_size": batch_size, "lr": lr,
                        "weight_decay": weight_decay, "patch_size": patch_size,
                        "stride": stride, "seed": seed,
                    },
                    "scene_ids": sorted(set(train_scenes + val_scenes), key=lambda x: int(x)),
                    "loss_configuration": {
                        "bce_weight": bce_weight, "dice_weight": dice_weight,
                        "pos_weight": pos_weight, "batch_dice": True,
                    },
                    "parameter_count": model.num_parameters,
                    "train_scenes": train_scenes,
                    "val_scenes": val_scenes,
                    "config": {
                        "patch_size": patch_size,
                        "stride": stride,
                        "batch_size": batch_size,
                        "lr": lr,
                        "bce_weight": bce_weight,
                        "dice_weight": dice_weight, "pos_weight": pos_weight,
                    },
                }
            temporary_path = ckpt_path.with_suffix(ckpt_path.suffix + ".tmp")
            torch.save(payload, temporary_path)
            os.replace(temporary_path, ckpt_path)

        best_flag = "*" if is_best else ""
        print(
            f"{epoch:>5} | "
            f"{tr_loss:>10.4f} | "
            f"{va_loss:>10.4f} | "
            f"{tr_dice:>10.4f} | "
            f"{va_dice:>10.4f} | "
            f"{tr_iou:>10.4f} | "
            f"{va_iou:>10.4f} | "
            f"{val_metrics['precision']:>9.4f} | "
            f"{val_metrics['recall']:>8.4f} | "
            f"{best_flag:>5}"
        )
        print(
            f"      validation probabilities: mean={val_metrics['probability_mean']:.4f}, "
            f"min={val_metrics['probability_min']:.4f}, max={val_metrics['probability_max']:.4f}"
        )

        history.append({
            "epoch": epoch,
            "train_loss": tr_loss,
            "val_loss": va_loss,
            "train_dice": tr_dice,
            "val_dice": va_dice,
            "train_iou": tr_iou,
            "val_iou": va_iou,
            "train_precision": train_metrics["precision"],
            "train_recall": train_metrics["recall"],
            "val_precision": val_metrics["precision"],
            "val_recall": val_metrics["recall"],
            "val_probability_mean": val_metrics["probability_mean"],
            "val_probability_min": val_metrics["probability_min"],
            "val_probability_max": val_metrics["probability_max"],
            "is_best": is_best,
        })

    print("=" * 75)
    print(f"\n[Training Completed]")
    print(f"  Best Epoch:           {best_epoch}")
    print(f"  Best Val Dice:        {best_val_dice:.4f}")
    print(f"  Best Val IoU:         {best_val_iou:.4f}")
    print(f"  Checkpoint Saved:     {ckpt_path} (exists={ckpt_path.is_file()})")

    return {
        "train_scenes": train_scenes,
        "val_scenes": val_scenes,
        "num_train_patches": len(train_data),
        "num_val_patches": len(val_data),
        "param_count": model.num_parameters,
        "best_epoch": best_epoch,
        "best_val_dice": best_val_dice,
        "best_val_iou": best_val_iou,
        "checkpoint_path": str(ckpt_path),
        "history": history,
    }


def train_final_s1s2_water(
    root_dir: str | Path,
    scene_ids: list[str],
    checkpoint_path: str | Path,
    *,
    epochs: int = 5,
    batch_size: int = 8,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    patch_size: int = 256,
    stride: int = 256,
    bce_weight: float = 1.0,
    dice_weight: float = 1.0,
    pos_weight: float = 2.0,
    seed: int = 42,
    device: str | None = None,
) -> dict[str, Any]:
    """Train the selected configuration on every supplied scene.

    This deliberately has no validation set: its metrics are training-only and
    must never be presented as held-out generalization.
    """
    _set_seed(seed)
    requested_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    dev = torch.device(requested_device)
    if dev.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but this PyTorch build has no available CUDA device.")

    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    dataset = S1S2WaterDataset(
        root_dir=root_dir, scene_ids=scene_ids, patch_size=patch_size, stride=stride,
        augment=True, normalization_config=DEFAULT_NORM_CONFIG,
    )
    loader = DataLoader(
        dataset, batch_size=batch_size, shuffle=True, num_workers=0,
        collate_fn=_collate_patches, pin_memory=(dev.type == "cuda"),
    )
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=32).to(dev)
    criterion = MaskedWaterLoss(
        bce_weight=bce_weight, dice_weight=dice_weight, pos_weight=pos_weight, batch_dice=True,
    )
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)
    history: list[dict[str, Any]] = []

    print("Final all-scene training: no held-out validation metrics will be reported.")
    print(f"Scenes: {scene_ids} | Patches: {len(dataset):,} | pos_weight: {pos_weight}")
    for epoch in range(1, epochs + 1):
        metrics = run_epoch_detailed(model, loader, criterion, dev, optimizer)
        scheduler.step()
        history.append({"epoch": epoch, **metrics})
        print(
            f"{epoch:>5} | Train loss {metrics['loss']:.4f} | Train Dice {metrics['dice']:.4f} | "
            f"Train IoU {metrics['iou']:.4f} | Prob mean {metrics['probability_mean']:.4f}"
        )

    payload = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "epoch": epochs,
        "normalization_config": DEFAULT_NORM_CONFIG.to_dict(),
        "model_config": {"s1_channels": 2, "s2_channels": 6, "base_channels": 32},
        "training_config": {
            "epochs": epochs, "batch_size": batch_size, "lr": lr,
            "weight_decay": weight_decay, "patch_size": patch_size, "stride": stride, "seed": seed,
        },
        "scene_ids": list(scene_ids),
        "train_scenes": list(scene_ids),
        "val_scenes": [],
        "training_mode": "final_all_scenes_no_heldout_validation",
        "loss_configuration": {
            "bce_weight": bce_weight, "dice_weight": dice_weight,
            "pos_weight": pos_weight, "batch_dice": True,
        },
        "parameter_count": model.num_parameters,
        "history": history,
    }
    temporary = checkpoint.with_suffix(checkpoint.suffix + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, checkpoint)
    return {"checkpoint_path": str(checkpoint), "num_train_patches": len(dataset), "history": history}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train OpticalSarFusionSegmenter on S1S2-Water.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("S1S2_WATER_ROOT", "/content/S1S2-Water")),
        help="Path to S1S2-Water dataset root",
    )
    parser.add_argument("--scenes", nargs="+", default=["1", "5", "6", "7", "8"], help="Available scene IDs")
    parser.add_argument("--train-scenes", nargs="+", default=None, help="Explicit train scene IDs")
    parser.add_argument("--val-scenes", nargs="+", default=None, help="Explicit val scene IDs")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--pos-weight", type=float, default=1.0, help="Positive BCE weight")
    parser.add_argument("--patch-size", type=int, default=256, help="Patch size")
    parser.add_argument("--stride", type=int, default=256, help="Patch stride")
    parser.add_argument("--max-train-patches", type=int, default=None, help="Max train patches per epoch")
    parser.add_argument("--max-val-patches", type=int, default=None, help="Max val patches")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("checkpoints/optical_sar_water.pt"),
        help="Path to save best checkpoint",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--device", type=str, default=None, help="Compute device (cuda or cpu)")
    parser.add_argument("--ignore-missing", action="store_true", help="Ignore missing scenes")
    parser.add_argument(
        "--final-train", action="store_true",
        help="Train on all selected scenes without a validation set; metrics are training-only.",
    )
    args = parser.parse_args()

    # Check if real data directory exists
    if not args.data.is_dir():
        print(f"[INFO] Dataset root {args.data} not found on this machine.")
        print("To run local unit tests with synthetic scenes, execute:")
        print("  python -m pytest training/tests/test_training.py -v")
        return

    # Check availability of requested scenes
    avail = inspect_scene_availability(args.data, args.scenes)
    available_scenes = avail["available"]
    print(f"Available scenes under {args.data}: {available_scenes}")

    if args.final_train:
        if args.val_scenes:
            raise SystemExit("--final-train cannot be combined with --val-scenes.")
        final_scenes = [str(s) for s in (args.train_scenes or available_scenes)]
        if set(final_scenes) != set(available_scenes):
            raise SystemExit(f"Final scenes must be all available scenes: {available_scenes}")
        results = train_final_s1s2_water(
            root_dir=args.data, scene_ids=final_scenes, checkpoint_path=args.checkpoint,
            epochs=args.epochs, batch_size=args.batch_size, lr=args.lr,
            pos_weight=args.pos_weight, patch_size=args.patch_size, stride=args.stride,
            seed=args.seed, device=args.device,
        )
        print("\nFinal-training summary (training metrics only):")
        print(json.dumps(results, indent=2))
        return

    train_scenes, val_scenes, split_src = resolve_scene_level_splits(
        root_dir=args.data,
        scene_ids=available_scenes,
        explicit_train=args.train_scenes,
        explicit_val=args.val_scenes,
    )
    print(f"Split Source: {split_src}")
    print(f"Train scenes: {train_scenes}")
    print(f"Val scenes:   {val_scenes}")

    results = train_s1s2_water(
        root_dir=args.data,
        train_scenes=train_scenes,
        val_scenes=val_scenes,
        checkpoint_path=args.checkpoint,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        pos_weight=args.pos_weight,
        patch_size=args.patch_size,
        stride=args.stride,
        max_train_patches=args.max_train_patches,
        max_val_patches=args.max_val_patches,
        seed=args.seed,
        device=args.device,
        ignore_missing=args.ignore_missing,
    )

    print("\nSummary Results:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

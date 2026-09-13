"""train.py — LEVIR-CD bi-temporal change detection training script.

Usage (Colab):
    !python change_detection_training/train.py
    !python change_detection_training/train.py --resume
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import torch
import torch.cuda.amp as amp
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from change_detection_training.dataset import build_loader
from change_detection_training.model import CombinedLoss, SiameseChangeDetector
from change_detection_training.utils import ChangeMetrics, load_config, set_seed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_device(device: torch.device) -> None:
    if device.type == "cuda":
        name = torch.cuda.get_device_name(device)
        mem  = torch.cuda.get_device_properties(device).total_memory / 1024 ** 3
        print(f"Device: {name}  ({mem:.1f} GB)")
    else:
        print("Device: CPU  (no CUDA detected)")


def _save_checkpoint(
    path: Path,
    model: SiameseChangeDetector,
    optimizer: AdamW,
    epoch: int,
    best_f1: float,
    config: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict":     model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "epoch":                epoch,
            "best_f1":              best_f1,
            "config":               config,
        },
        path,
    )


def _load_checkpoint(
    path: Path,
    model: SiameseChangeDetector,
    optimizer: AdamW,
    device: torch.device,
) -> tuple[int, float]:
    """Load checkpoint and return (start_epoch, best_f1)."""
    ckpt = torch.load(path, map_location=device)
    model.load_state_dict(ckpt["model_state_dict"])
    optimizer.load_state_dict(ckpt["optimizer_state_dict"])
    epoch   = ckpt.get("epoch", 0)
    best_f1 = ckpt.get("best_f1", 0.0)
    print(f"Resumed from epoch {epoch}  (best F1 so far: {best_f1:.4f})")
    return epoch, best_f1


# ---------------------------------------------------------------------------
# One epoch
# ---------------------------------------------------------------------------

def _run_epoch(
    model: SiameseChangeDetector,
    loader: torch.utils.data.DataLoader,
    criterion: CombinedLoss,
    device: torch.device,
    optimizer: AdamW | None,
    scaler: amp.GradScaler,
    metrics: ChangeMetrics,
) -> float:
    """Run one training or validation epoch.  Returns mean loss."""
    training = optimizer is not None
    model.train() if training else model.eval()
    metrics.reset()

    total_loss = 0.0
    total_samples = 0

    ctx = torch.enable_grad() if training else torch.no_grad()
    with ctx:
        for batch in loader:
            img_a  = batch["image_a"].to(device, non_blocking=True)
            img_b  = batch["image_b"].to(device, non_blocking=True)
            mask   = batch["mask"].to(device, non_blocking=True)

            with amp.autocast(enabled=(device.type == "cuda")):
                logits = model(img_a, img_b)
                loss   = criterion(logits, mask)

            if training:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()

            bs = img_a.size(0)
            total_loss    += loss.detach().item() * bs
            total_samples += bs
            metrics.update(logits.detach(), mask)

    return total_loss / max(total_samples, 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def train(resume: bool = False) -> None:
    cfg    = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _print_device(device)
    set_seed(cfg["seed"])

    # DataLoaders
    train_loader = build_loader(
        cfg["dataset_root"], "train",
        image_size=cfg["image_size"],
        batch_size=cfg["batch_size"],
        num_workers=cfg["num_workers"],
    )
    val_loader = build_loader(
        cfg["dataset_root"], "val",
        image_size=cfg["image_size"],
        batch_size=cfg["batch_size"],
        num_workers=cfg["num_workers"],
    )
    print(f"Train batches: {len(train_loader)}  |  Val batches: {len(val_loader)}")

    # Model
    model = SiameseChangeDetector(in_channels=3, base_channels=32).to(device)
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Trainable parameters: {total_params:,}")

    # Loss — estimate positive weight from first few batches to handle imbalance
    pos_weight = torch.tensor([5.0], device=device)   # changed pixels are rare
    criterion  = CombinedLoss(dice_weight=cfg["dice_weight"], pos_weight=pos_weight)

    optimizer = AdamW(
        model.parameters(),
        lr=cfg["learning_rate"],
        weight_decay=cfg["weight_decay"],
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=cfg["epochs"], eta_min=1e-6)
    scaler    = amp.GradScaler(enabled=(device.type == "cuda"))

    ckpt_dir  = Path(cfg["checkpoint_dir"])
    best_path = ckpt_dir / "best_model.pth"
    last_path = ckpt_dir / "last_model.pth"

    start_epoch = 0
    best_f1     = 0.0

    if resume and last_path.is_file():
        start_epoch, best_f1 = _load_checkpoint(last_path, model, optimizer, device)

    train_metrics = ChangeMetrics(threshold=cfg["threshold"])
    val_metrics   = ChangeMetrics(threshold=cfg["threshold"])

    # -----------------------------------------------------------------------
    for epoch in range(start_epoch + 1, cfg["epochs"] + 1):
        t0 = time.time()

        train_loss = _run_epoch(model, train_loader, criterion, device, optimizer, scaler, train_metrics)
        val_loss   = _run_epoch(model, val_loader,   criterion, device, None,      scaler, val_metrics)

        scheduler.step()

        tm = train_metrics.compute()
        vm = val_metrics.compute()
        elapsed = time.time() - t0

        print(
            f"Epoch {epoch:02d}/{cfg['epochs']:02d}  "
            f"({elapsed:.0f}s)  "
            f"Train Loss: {train_loss:.4f}  "
            f"Val Loss: {val_loss:.4f}  |  "
            f"Precision: {vm['precision']:.4f}  "
            f"Recall: {vm['recall']:.4f}  "
            f"F1: {vm['f1']:.4f}  "
            f"IoU: {vm['iou']:.4f}"
        )

        # Save last checkpoint every epoch (enables resume)
        _save_checkpoint(last_path, model, optimizer, epoch, best_f1, cfg)

        # Save best checkpoint when validation F1 improves
        if vm["f1"] > best_f1:
            best_f1 = vm["f1"]
            _save_checkpoint(best_path, model, optimizer, epoch, best_f1, cfg)
            print(f"  ✓ New best F1: {best_f1:.4f}  → saved to {best_path}")

    print(f"\nTraining complete.  Best validation F1: {best_f1:.4f}")
    print(f"Best checkpoint: {best_path}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LEVIR-CD change detector.")
    parser.add_argument("--resume", action="store_true", help="Resume from last_model.pth")
    args = parser.parse_args()
    train(resume=args.resume)

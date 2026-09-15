"""utils.py — shared helpers: metrics, seeding, config, visualisation."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def set_seed(seed: int = 42) -> None:
    """Set Python / NumPy / PyTorch seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml.  Falls back to built-in defaults if file not found."""
    defaults: dict[str, Any] = {
        "dataset_root":   "/content/LEVIR-CD-clean",
        "checkpoint_dir": "/content/drive/MyDrive/bi_temporal_change/checkpoints",
        "image_size":     256,
        "batch_size":     8,
        "num_workers":    2,
        "epochs":         30,
        "learning_rate":  1e-4,
        "weight_decay":   1e-4,
        "dice_weight":    1.0,
        "threshold":      0.5,
        "seed":           42,
    }
    if path is None:
        path = Path(__file__).parent / "config.yaml"
    path = Path(path)
    if not path.is_file():
        return defaults
    try:
        import yaml  # type: ignore[import]
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        defaults.update({k: v for k, v in data.items() if v is not None})
    except Exception as exc:  # noqa: BLE001
        print(f"[config] Could not load {path}: {exc} — using defaults.")
    return defaults


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class ChangeMetrics:
    """Accumulate TP / FP / FN / TN over batches, then compute final metrics."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self.tp = self.fp = self.fn = self.tn = 0

    def reset(self) -> None:
        self.tp = self.fp = self.fn = self.tn = 0

    def update(self, logits: Tensor, targets: Tensor) -> None:
        """Update counts from a batch of logits and binary targets."""
        preds   = (torch.sigmoid(logits) >= self.threshold).long().cpu()
        targets = targets.long().cpu()
        self.tp += int((preds * targets).sum())
        self.fp += int((preds * (1 - targets)).sum())
        self.fn += int(((1 - preds) * targets).sum())
        self.tn += int(((1 - preds) * (1 - targets)).sum())

    def compute(self) -> dict[str, float]:
        eps = 1e-8
        precision = self.tp / (self.tp + self.fp + eps)
        recall    = self.tp / (self.tp + self.fn + eps)
        f1        = 2 * precision * recall / (precision + recall + eps)
        iou       = self.tp / (self.tp + self.fp + self.fn + eps)
        return {
            "precision": precision,
            "recall":    recall,
            "f1":        f1,
            "iou":       iou,
            "tp":        self.tp,
            "fp":        self.fp,
            "fn":        self.fn,
            "tn":        self.tn,
        }


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def _denorm(tensor: Tensor) -> np.ndarray:
    """Reverse ImageNet normalisation and return HWC uint8 array."""
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    img  = tensor.cpu().numpy().transpose(1, 2, 0)   # CHW → HWC
    img  = img * std + mean
    img  = np.clip(img * 255, 0, 255).astype(np.uint8)
    return img


def visualise_sample(
    image_a: Tensor,
    image_b: Tensor,
    mask: Tensor,
    logits: Tensor,
    filename: str = "",
    save_path: str | Path | None = None,
) -> None:
    """Display or save a 5-panel figure: T1 | T2 | GT | Pred | Prob."""
    try:
        import matplotlib
        matplotlib.use("Agg")          # safe for Colab / headless
        import matplotlib.pyplot as plt
    except ImportError:
        print("[visualise] matplotlib not available — skipping plot.")
        return

    prob = torch.sigmoid(logits[0, 0]).cpu().numpy()
    pred = (prob >= 0.5).astype(np.uint8)
    gt   = mask[0, 0].cpu().numpy().astype(np.uint8)

    fig, axes = plt.subplots(1, 5, figsize=(20, 4))
    titles = ["T1 (A)", "T2 (B)", "Ground Truth", "Prediction", "Probability"]
    images = [
        _denorm(image_a[0]),
        _denorm(image_b[0]),
        gt,
        pred,
        prob,
    ]
    cmaps = [None, None, "gray", "gray", "hot"]

    for ax, title, img, cmap in zip(axes, titles, images, cmaps):
        ax.imshow(img, cmap=cmap, vmin=0, vmax=1 if img.dtype == np.float32 else None)
        ax.set_title(title, fontsize=10)
        ax.axis("off")

    if filename:
        fig.suptitle(filename, fontsize=9)
    plt.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=100, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()

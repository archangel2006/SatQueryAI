from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


def masked_bce_loss(
    logits: Tensor, targets: Tensor, valid: Tensor, pos_weight: float = 1.0
) -> Tensor:
    """Compute Binary Cross Entropy with Logits exclusively over valid pixels."""
    if logits.ndim == 3:
        logits = logits.unsqueeze(1)
    if targets.ndim == 3:
        targets = targets.unsqueeze(1)
    if valid.ndim == 3:
        valid = valid.unsqueeze(1)

    valid_mask = (valid > 0.5)
    valid_count = valid_mask.sum()
    if valid_count == 0:
        return torch.tensor(0.0, device=logits.device, requires_grad=True)

    # Construct this on the logits device so the loss works unchanged on CPU/CUDA.
    weight = torch.as_tensor(pos_weight, dtype=logits.dtype, device=logits.device)
    bce = F.binary_cross_entropy_with_logits(
        logits, targets, reduction="none", pos_weight=weight
    )
    return (bce * valid_mask.float()).sum() / valid_count.clamp(min=1.0)


def masked_dice_loss(
    logits: Tensor,
    targets: Tensor,
    valid: Tensor,
    smooth: float = 1e-6,
    batch_dice: bool = True,
) -> Tensor:
    """Compute soft Dice loss exclusively over valid pixels.

    When batch_dice=True (default), intersection and cardinality are summed
    across the entire batch before computing the ratio. This prevents empty-foreground
    patches (very common in satellite imagery) from artificially blowing up the loss
    when the model correctly predicts near-zero probabilities.
    """
    if logits.ndim == 3:
        logits = logits.unsqueeze(1)
    if targets.ndim == 3:
        targets = targets.unsqueeze(1)
    if valid.ndim == 3:
        valid = valid.unsqueeze(1)

    valid_mask = (valid > 0.5).float()
    probs = torch.sigmoid(logits) * valid_mask
    targets = (targets > 0.5).float() * valid_mask

    if batch_dice:
        intersection = (probs * targets).sum()
        cardinality = (probs + targets).sum()
        valid_sum = valid_mask.sum()
        if valid_sum == 0:
            return torch.tensor(0.0, device=logits.device, requires_grad=True)
        dice = (2.0 * intersection + smooth) / (cardinality + smooth)
        return 1.0 - dice

    # Per-sample Dice
    intersection = (probs * targets).sum(dim=(-2, -1))
    cardinality = (probs + targets).sum(dim=(-2, -1))
    valid_sum = valid_mask.sum(dim=(-2, -1))
    dice = (2.0 * intersection + smooth) / (cardinality + smooth)
    has_valid = valid_sum > 0
    if has_valid.any():
        return (1.0 - dice[has_valid]).mean()
    return torch.tensor(0.0, device=logits.device, requires_grad=True)


class MaskedWaterLoss(nn.Module):
    """Combined BCEWithLogitsLoss + DiceLoss for binary water segmentation.

    Excludes invalid / nodata pixels via the provided valid mask.
    """

    def __init__(
        self,
        bce_weight: float = 1.0,
        dice_weight: float = 1.0,
        pos_weight: float = 1.0,
        smooth: float = 1e-6,
        batch_dice: bool = True,
    ) -> None:
        super().__init__()
        self.bce_weight = bce_weight
        self.dice_weight = dice_weight
        self.pos_weight = pos_weight
        self.smooth = smooth
        self.batch_dice = batch_dice

    def forward(
        self,
        logits: Tensor,
        targets: Tensor,
        valid: Tensor,
    ) -> tuple[Tensor, dict[str, float]]:
        bce = masked_bce_loss(logits, targets, valid, pos_weight=self.pos_weight)
        dice = masked_dice_loss(
            logits, targets, valid, smooth=self.smooth, batch_dice=self.batch_dice
        )
        total = self.bce_weight * bce + self.dice_weight * dice
        metrics = {
            "loss_total": float(total.detach().item()),
            "loss_bce": float(bce.detach().item()),
            "loss_dice": float(dice.detach().item()),
        }
        return total, metrics


def masked_confusion_counts(
    logits: Tensor, targets: Tensor, valid: Tensor, threshold: float = 0.5
) -> dict[str, int]:
    """Return global binary confusion counts, considering valid pixels only."""
    if logits.ndim == 3:
        logits = logits.unsqueeze(1)
    if targets.ndim == 3:
        targets = targets.unsqueeze(1)
    if valid.ndim == 3:
        valid = valid.unsqueeze(1)
    valid_mask = valid > 0.5
    preds = (torch.sigmoid(logits) > threshold) & valid_mask
    targets_valid = (targets > 0.5) & valid_mask
    return {
        "tp": int((preds & targets_valid).sum().item()),
        "fp": int((preds & ~targets_valid & valid_mask).sum().item()),
        "fn": int((~preds & targets_valid & valid_mask).sum().item()),
        "tn": int((~preds & ~targets_valid & valid_mask).sum().item()),
        "valid_pixels": int(valid_mask.sum().item()),
    }


def metrics_from_counts(counts: dict[str, int], smooth: float = 1e-6) -> dict[str, float]:
    """Compute segmentation metrics from counts accumulated across all patches."""
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    dice = (2.0 * tp + smooth) / (2.0 * tp + fp + fn + smooth)
    iou = (tp + smooth) / (tp + fp + fn + smooth)
    precision = (tp + smooth) / (tp + fp + smooth)
    recall = (tp + smooth) / (tp + fn + smooth)
    return {"dice": float(dice), "iou": float(iou), "precision": float(precision), "recall": float(recall)}


def compute_masked_metrics(
    logits: Tensor,
    targets: Tensor,
    valid: Tensor,
    threshold: float = 0.5,
    smooth: float = 1e-6,
) -> dict[str, float]:
    """Compute Dice score and Intersection-over-Union (IoU) over valid pixels."""
    with torch.no_grad():
        if logits.ndim == 3:
            logits = logits.unsqueeze(1)
        if targets.ndim == 3:
            targets = targets.unsqueeze(1)
        if valid.ndim == 3:
            valid = valid.unsqueeze(1)

        counts = masked_confusion_counts(logits, targets, valid, threshold)
        result = metrics_from_counts(counts, smooth)
        result.update(counts)
        result["water_pixels_pred"] = counts["tp"] + counts["fp"]
        result["water_pixels_gt"] = counts["tp"] + counts["fn"]
        return result

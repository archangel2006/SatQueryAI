from __future__ import annotations

import pytest
import torch

from training.fusion_model import OpticalSarFusionSegmenter
from training.losses import (
    MaskedWaterLoss,
    compute_masked_metrics,
    masked_bce_loss,
    masked_dice_loss,
)
from training.overfit_test import run_4_patch_overfit, run_forward_pass_check


def test_optical_sar_fusion_segmenter_shapes() -> None:
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=32)
    s1 = torch.randn(2, 2, 256, 256)
    s2 = torch.randn(2, 6, 256, 256)

    logits = model(s1, s2)
    assert logits.shape == (2, 1, 256, 256)
    assert logits.dtype == torch.float32

    probs = model.predict_probability(s1, s2)
    assert probs.shape == (2, 1, 256, 256)
    assert (probs >= 0.0).all() and (probs <= 1.0).all()

    mask = model.predict_mask(s1, s2, threshold=0.5)
    assert mask.shape == (2, 1, 256, 256)
    assert set(torch.unique(mask).tolist()).issubset({0.0, 1.0})


def test_model_parameter_count() -> None:
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=32)
    params = model.num_parameters
    # Should be around 3.5M parameters
    assert 2_000_000 < params < 5_000_000


def test_masked_bce_and_dice_loss() -> None:
    logits = torch.randn(2, 1, 64, 64)
    targets = torch.randint(0, 2, (2, 1, 64, 64)).float()
    valid = torch.ones(2, 1, 64, 64)
    # Set half of pixels to invalid
    valid[:, :, :32, :] = 0.0

    bce = masked_bce_loss(logits, targets, valid)
    assert torch.isfinite(bce)
    assert bce.item() > 0.0

    dice = masked_dice_loss(logits, targets, valid)
    assert torch.isfinite(dice)
    assert 0.0 <= dice.item() <= 1.0

    criterion = MaskedWaterLoss(bce_weight=1.0, dice_weight=1.0)
    total, metrics = criterion(logits, targets, valid)
    assert torch.isfinite(total)
    assert "loss_bce" in metrics
    assert "loss_dice" in metrics


def test_compute_masked_metrics() -> None:
    logits = torch.tensor([[[[5.0, -5.0], [-5.0, 5.0]]]])  # sigmoid -> ~[1, 0, 0, 1]
    targets = torch.tensor([[[[1.0, 0.0], [0.0, 1.0]]]])
    valid = torch.tensor([[[[1.0, 1.0], [1.0, 0.0]]]])  # bottom-right is invalid

    metrics = compute_masked_metrics(logits, targets, valid, threshold=0.5)
    # Top-left is water match (1, 1). Top-right is non-water match (0, 0).
    # Bottom-left is non-water match (0, 0). Bottom-right is masked out.
    assert metrics["valid_pixels"] == 3
    assert metrics["dice"] > 0.95
    assert metrics["iou"] > 0.95


def test_forward_pass_check_and_gradients() -> None:
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=16)
    s1 = torch.randn(2, 2, 64, 64)
    s2 = torch.randn(2, 6, 64, 64)
    mask = torch.randint(0, 2, (2, 1, 64, 64)).float()
    valid = torch.ones(2, 1, 64, 64)

    criterion = MaskedWaterLoss()
    result = run_forward_pass_check(model, s1, s2, mask, valid, criterion)

    assert result["shape_ok"]
    assert result["loss_finite"]
    assert result["s1_gradient_ok"]
    assert result["s2_gradient_ok"]
    assert result["head_gradient_ok"]


def test_4_patch_overfit_convergence() -> None:
    torch.manual_seed(42)
    # Lightweight model for test speed
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=16)

    # 4 synthetic patches with distinct water patterns
    s1 = torch.randn(4, 2, 64, 64)
    s2 = torch.randn(4, 6, 64, 64)
    mask = torch.zeros(4, 1, 64, 64)
    mask[0, :, 10:30, 10:30] = 1.0
    mask[1, :, 20:40, 20:50] = 1.0
    mask[2, :, 5:25, 40:60] = 1.0
    mask[3, :, 35:55, 5:25] = 1.0
    valid = torch.ones(4, 1, 64, 64)

    criterion = MaskedWaterLoss(bce_weight=1.0, dice_weight=1.0)
    history = run_4_patch_overfit(
        model=model,
        s1_batch=s1,
        s2_batch=s2,
        mask_batch=mask,
        valid_batch=valid,
        criterion=criterion,
        num_steps=40,
        lr=5e-3,
        device=torch.device("cpu"),
    )

    initial = history[0]
    final = history[-1]

    # Confirm strong loss reduction and strong Dice increase
    assert final["loss"] < initial["loss"] * 0.4
    assert final["dice"] > 0.85
    assert final["iou"] > 0.75


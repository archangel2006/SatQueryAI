from __future__ import annotations

import torch

from training.diagnose import evaluate_threshold_sweep
from training.loso import leave_one_scene_out_splits
from training.losses import MaskedWaterLoss, compute_masked_metrics


def test_metrics_ignore_invalid_pixels_and_include_precision_recall() -> None:
    logits = torch.tensor([[[[8.0, 8.0], [-8.0, -8.0]]]])
    targets = torch.tensor([[[[1.0, 0.0], [1.0, 0.0]]]])
    # The false positive at [0, 1] is nodata and must not count.
    valid = torch.tensor([[[[1.0, 0.0], [1.0, 1.0]]]])
    metrics = compute_masked_metrics(logits, targets, valid)
    assert metrics["tp"] == 1 and metrics["fp"] == 0 and metrics["fn"] == 1
    assert 0.66 < metrics["dice"] < 0.67
    assert metrics["precision"] > 0.99
    assert 0.49 < metrics["recall"] < 0.51


def test_weighted_bce_changes_only_positive_term() -> None:
    logits = torch.zeros(1, 1, 1, 2)
    targets = torch.tensor([[[[1.0, 0.0]]]])
    valid = torch.ones_like(targets)
    unweighted, _ = MaskedWaterLoss(dice_weight=0.0, pos_weight=1.0)(logits, targets, valid)
    weighted, _ = MaskedWaterLoss(dice_weight=0.0, pos_weight=2.0)(logits, targets, valid)
    assert weighted > unweighted
    assert torch.isclose(weighted, unweighted * 1.5)


def test_threshold_sweep_uses_valid_pixels_and_reports_all_metrics() -> None:
    probs = torch.tensor([[[[0.9, 0.9]]]])
    targets = torch.tensor([[[[1.0, 0.0]]]])
    valid = torch.tensor([[[[1, 0]]]], dtype=torch.bool)
    row = evaluate_threshold_sweep(probs, targets, valid)["0.5"]
    assert row["dice"] > 0.99 and row["precision"] > 0.99 and row["recall"] > 0.99


def test_loso_splits_are_exhaustive_and_leak_free() -> None:
    splits = leave_one_scene_out_splits()
    assert len(splits) == 5
    assert {val[0] for _, val in splits} == {"1", "5", "6", "7", "8"}
    for train, val in splits:
        assert len(train) == 4
        assert not set(train) & set(val)

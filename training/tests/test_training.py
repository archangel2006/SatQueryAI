from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from training.evaluate import evaluate_dataset, load_optical_sar_model
from training.tests.test_s1s2_water_dataset import _make_synthetic_scene
from training.train import resolve_scene_level_splits, train_s1s2_water


@pytest.fixture()
def training_scene_root(tmp_path: Path) -> Path:
    # Create 5 synthetic scenes matching S1S2-Water scene IDs: 1, 5, 6, 7, 8
    _make_synthetic_scene(tmp_path, "1", split="train")
    _make_synthetic_scene(tmp_path, "5", split="train")
    _make_synthetic_scene(tmp_path, "6", split="train")
    _make_synthetic_scene(tmp_path, "7", split="train")
    _make_synthetic_scene(tmp_path, "8", split="val")
    return tmp_path


def test_resolve_scene_splits(training_scene_root: Path) -> None:
    scenes = ["1", "5", "6", "7", "8"]

    # 1. Automatic resolution from metadata
    train_s, val_s, src = resolve_scene_level_splits(training_scene_root, scenes)
    assert set(train_s) == {"1", "5", "6", "7"}
    assert set(val_s) == {"8"}
    assert "metadata" in src or "fallback" in src
    assert len(set(train_s).intersection(set(val_s))) == 0

    # 2. Explicit splits
    train_exp, val_exp, src_exp = resolve_scene_level_splits(
        training_scene_root, scenes, explicit_train=["1", "5"], explicit_val=["6", "7", "8"]
    )
    assert train_exp == ["1", "5"]
    assert val_exp == ["6", "7", "8"]
    assert src_exp == "explicit_cli_arguments"

    # 3. Leakage error detection
    with pytest.raises(ValueError, match="Spatial leakage"):
        resolve_scene_level_splits(
            training_scene_root, scenes, explicit_train=["1", "5"], explicit_val=["5", "8"]
        )


def test_full_training_and_checkpoint_lifecycle(training_scene_root: Path, tmp_path: Path) -> None:
    ckpt_path = tmp_path / "checkpoints" / "test_optical_sar_water.pt"

    results = train_s1s2_water(
        root_dir=training_scene_root,
        train_scenes=["1", "5", "6", "7"],
        val_scenes=["8"],
        checkpoint_path=ckpt_path,
        epochs=2,
        batch_size=4,
        lr=3e-3,
        patch_size=128,
        stride=128,
        max_train_patches=8,
        max_val_patches=4,
        seed=42,
        device="cpu",
    )

    # 1. Verify training results
    assert results["num_train_patches"] > 0
    assert results["num_val_patches"] > 0
    assert len(results["history"]) == 2
    assert results["best_epoch"] in (1, 2)
    assert results["best_val_dice"] > 0.0

    # 2. Verify checkpoint was saved
    assert ckpt_path.is_file()
    assert ckpt_path.stat().st_size > 100_000

    # 3. Verify checkpoint loading
    model, metadata = load_optical_sar_model(ckpt_path, device=torch.device("cpu"))
    assert metadata["epoch"] in (1, 2)
    assert metadata["train_scenes"] == ["1", "5", "6", "7"]
    assert metadata["val_scenes"] == ["8"]
    assert "normalization_config" in metadata
    assert metadata["model_config"] == {"s1_channels": 2, "s2_channels": 6, "base_channels": 32}
    assert metadata["training_config"]["seed"] == 42
    assert metadata["loss_configuration"]["pos_weight"] == 1.0
    assert metadata["scene_ids"] == ["1", "5", "6", "7", "8"]
    assert metadata["parameter_count"] > 0

    # 4. Forward pass with loaded model
    s1 = torch.randn(2, 2, 128, 128)
    s2 = torch.randn(2, 6, 128, 128)
    logits = model(s1, s2)
    assert logits.shape == (2, 1, 128, 128)

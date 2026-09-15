from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.optim as optim
from torch.utils.data import DataLoader

from training.fusion_model import OpticalSarFusionSegmenter
from training.losses import MaskedWaterLoss, compute_masked_metrics
from training.s1s2_water_dataset import DEFAULT_NORM_CONFIG, S1S2WaterDataset


def run_forward_pass_check(
    model: OpticalSarFusionSegmenter,
    s1: torch.Tensor,
    s2: torch.Tensor,
    mask: torch.Tensor,
    valid: torch.Tensor,
    criterion: MaskedWaterLoss,
) -> dict[str, Any]:
    """Verify batch forward pass, output shape, finite loss, and gradient flow."""
    model.train()
    model.zero_grad()

    # 1. Forward pass
    logits = model(s1, s2)
    expected_shape = (s1.shape[0], 1, s1.shape[2], s1.shape[3])
    shape_ok = tuple(logits.shape) == expected_shape

    # 2. Loss computation
    loss, loss_dict = criterion(logits, mask, valid)
    loss_finite = torch.isfinite(loss).item()

    # 3. Backward pass
    loss.backward()

    # 4. Check gradients in S1 encoder, S2 encoder, fusion, and head
    s1_grad = model.s1_enc0.block[0].weight.grad
    s2_grad = model.s2_enc0.block[0].weight.grad
    head_grad = model.head.weight.grad

    s1_grad_ok = s1_grad is not None and torch.isfinite(s1_grad).all().item() and (s1_grad.abs().sum().item() > 0)
    s2_grad_ok = s2_grad is not None and torch.isfinite(s2_grad).all().item() and (s2_grad.abs().sum().item() > 0)
    head_grad_ok = head_grad is not None and torch.isfinite(head_grad).all().item() and (head_grad.abs().sum().item() > 0)

    # 5. Metrics
    metrics = compute_masked_metrics(logits, mask, valid)

    return {
        "output_shape": tuple(logits.shape),
        "expected_shape": expected_shape,
        "shape_ok": shape_ok,
        "loss_finite": loss_finite,
        "loss_total": float(loss.item()),
        "loss_bce": loss_dict["loss_bce"],
        "loss_dice": loss_dict["loss_dice"],
        "s1_gradient_ok": s1_grad_ok,
        "s2_gradient_ok": s2_grad_ok,
        "head_gradient_ok": head_grad_ok,
        "initial_dice": metrics["dice"],
        "initial_iou": metrics["iou"],
    }


def run_4_patch_overfit(
    model: OpticalSarFusionSegmenter,
    s1_batch: torch.Tensor,
    s2_batch: torch.Tensor,
    mask_batch: torch.Tensor,
    valid_batch: torch.Tensor,
    criterion: MaskedWaterLoss,
    num_steps: int = 60,
    lr: float = 3e-3,
    device: torch.device | None = None,
) -> list[dict[str, Any]]:
    """Train the model repeatedly on exactly 4 patches to verify memorization capability."""
    dev = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(dev)
    s1_b = s1_batch.to(dev)
    s2_b = s2_batch.to(dev)
    mask_b = mask_batch.to(dev)
    valid_b = valid_batch.to(dev)

    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    history: list[dict[str, Any]] = []

    print(f"\n[4-Patch Overfit] Starting {num_steps} optimization steps on device '{dev}' (lr={lr})...")
    print(f"{'Step':>6} | {'Loss':>10} | {'BCE':>10} | {'Dice Loss':>10} | {'Dice Score':>10} | {'IoU':>10}")
    print("-" * 68)

    model.train()
    for step in range(1, num_steps + 1):
        optimizer.zero_grad()
        logits = model(s1_b, s2_b)
        loss, loss_dict = criterion(logits, mask_b, valid_b)
        loss.backward()
        optimizer.step()

        metrics = compute_masked_metrics(logits, mask_b, valid_b)
        record = {
            "step": step,
            "loss": float(loss.item()),
            "loss_bce": loss_dict["loss_bce"],
            "loss_dice": loss_dict["loss_dice"],
            "dice": metrics["dice"],
            "iou": metrics["iou"],
        }
        history.append(record)

        if step == 1 or step % 10 == 0 or step == num_steps:
            print(
                f"{step:>6} | "
                f"{record['loss']:>10.4f} | "
                f"{record['loss_bce']:>10.4f} | "
                f"{record['loss_dice']:>10.4f} | "
                f"{record['dice']:>10.4f} | "
                f"{record['iou']:>10.4f}"
            )

    return history


def main() -> None:
    parser = argparse.ArgumentParser(description="Optical+SAR Water Segmentation Forward Pass and 4-Patch Overfit Test.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("S1S2_WATER_ROOT", "/content/S1S2-Water")),
        help="Path to S1S2-Water dataset root",
    )
    parser.add_argument("--scene-ids", nargs="+", default=["1", "5", "6", "7", "8"], help="Scene IDs to load")
    parser.add_argument("--steps", type=int, default=60, help="Number of overfit iterations")
    parser.add_argument("--lr", type=float, default=3e-3, help="Learning rate for overfit test")
    parser.add_argument("--patch-size", type=int, default=256, help="Patch size (pixels)")
    parser.add_argument("--ignore-missing", action="store_true", help="Ignore missing scenes")
    args = parser.parse_args()

    print("=" * 70)
    print("Optical+SAR Water Segmentation â€” Forward Pass & 4-Patch Overfit")
    print("=" * 70)

    # 1. Instantiate model
    model = OpticalSarFusionSegmenter(s1_channels=2, s2_channels=6, base_channels=32)
    param_count = model.num_parameters
    print(f"\n[Model Initialized]")
    print(f"  Architecture:    OpticalSarFusionSegmenter (Dual-Encoder U-Net)")
    print(f"  S1 Channels:     2 (VV, VH)")
    print(f"  S2 Channels:     6 (Blue, Green, Red, NIR, SWIR1, SWIR2)")
    print(f"  Total Parameters: {param_count:,}")

    # 2. Dataset loading
    if not args.data.is_dir():
        print(f"\n[INFO] Dataset root {args.data} not found. Running with synthetic test dataset.")
        from training.tests.test_s1s2_water_dataset import _make_synthetic_scene
        import tempfile
        temp_dir = tempfile.TemporaryDirectory()
        data_root = Path(temp_dir.name)
        _make_synthetic_scene(data_root, "1")
        scene_ids = ["1"]
    else:
        data_root = args.data
        scene_ids = args.scene_ids

    dataset = S1S2WaterDataset(
        root_dir=data_root,
        scene_ids=scene_ids,
        patch_size=args.patch_size,
        stride=args.patch_size,
        augment=False,
        normalization_config=DEFAULT_NORM_CONFIG,
        ignore_missing=args.ignore_missing or (data_root != args.data),
    )

    print(f"\n[Dataset Loaded]")
    print(f"  Available patches: {len(dataset)}")
    if len(dataset) < 4:
        raise ValueError(f"Need at least 4 patches for overfit test, but found {len(dataset)}.")

    # 3. Collate 4 patches
    patches = [dataset[i] for i in range(4)]
    s1_batch = torch.stack([p["s1"] for p in patches], dim=0)    # [4, 2, 256, 256]
    s2_batch = torch.stack([p["s2"] for p in patches], dim=0)    # [4, 6, 256, 256]
    mask_batch = torch.stack([p["mask"] for p in patches], dim=0).unsqueeze(1)  # [4, 1, 256, 256]
    valid_batch = torch.stack([p["valid"] for p in patches], dim=0).unsqueeze(1)  # [4, 1, 256, 256]

    print(f"\n[Batch Tensor Shapes]")
    print(f"  S1 Batch:    {tuple(s1_batch.shape)} (float32)")
    print(f"  S2 Batch:    {tuple(s2_batch.shape)} (float32)")
    print(f"  Mask Batch:  {tuple(mask_batch.shape)} (float32)")
    print(f"  Valid Batch: {tuple(valid_batch.shape)} (float32)")

    # 4. Check forward pass, loss, and gradients
    criterion = MaskedWaterLoss(bce_weight=1.0, dice_weight=1.0)
    fp_check = run_forward_pass_check(model, s1_batch, s2_batch, mask_batch, valid_batch, criterion)

    print(f"\n[Forward Pass Verification]")
    print(f"  Output Shape:      {fp_check['output_shape']} (matches {fp_check['expected_shape']}: {fp_check['shape_ok']})")
    print(f"  Loss Total:        {fp_check['loss_total']:.4f} (BCE: {fp_check['loss_bce']:.4f}, Dice: {fp_check['loss_dice']:.4f})")
    print(f"  Loss is Finite:    {fp_check['loss_finite']}")
    print(f"  S1 Grad Flowing:   {fp_check['s1_gradient_ok']}")
    print(f"  S2 Grad Flowing:   {fp_check['s2_gradient_ok']}")
    print(f"  Head Grad Flowing: {fp_check['head_gradient_ok']}")
    print(f"  Initial Dice / IoU: {fp_check['initial_dice']:.4f} / {fp_check['initial_iou']:.4f}")

    assert fp_check["shape_ok"], "Output shape mismatch!"
    assert fp_check["loss_finite"], "Loss is not finite!"
    assert fp_check["s1_gradient_ok"], "S1 gradient not flowing!"
    assert fp_check["s2_gradient_ok"], "S2 gradient not flowing!"
    assert fp_check["head_gradient_ok"], "Head gradient not flowing!"

    # 5. Run 4-patch overfit test
    history = run_4_patch_overfit(
        model=model,
        s1_batch=s1_batch,
        s2_batch=s2_batch,
        mask_batch=mask_batch,
        valid_batch=valid_batch,
        criterion=criterion,
        num_steps=args.steps,
        lr=args.lr,
    )

    initial = history[0]
    final = history[-1]
    print("\n" + "=" * 70)
    print("4-PATCH OVERFIT SUMMARY")
    print("=" * 70)
    print(f"Initial (Step 1):   Loss = {initial['loss']:.4f} | Dice = {initial['dice']:.4f} | IoU = {initial['iou']:.4f}")
    print(f"Final (Step {args.steps}):  Loss = {final['loss']:.4f} | Dice = {final['dice']:.4f} | IoU = {final['iou']:.4f}")

    loss_decreased = final["loss"] < initial["loss"] * 0.5
    dice_increased = final["dice"] > 0.80
    iou_increased = final["iou"] > 0.70

    print(f"Loss strongly decreased: {loss_decreased} ({initial['loss']:.4f} -> {final['loss']:.4f})")
    print(f"Dice strongly increased: {dice_increased} ({initial['dice']:.4f} -> {final['dice']:.4f})")
    print(f"IoU strongly increased:  {iou_increased} ({initial['iou']:.4f} -> {final['iou']:.4f})")
    print("=" * 70)

    if not (loss_decreased and dice_increased and iou_increased):
        print("[WARNING] Overfit criteria not fully met. Debugging recommended.")
    else:
        print("[SUCCESS] 4-patch overfit passed successfully!")


if __name__ == "__main__":
    main()


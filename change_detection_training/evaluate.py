"""evaluate.py — Evaluate best_model.pth on the LEVIR-CD test split.

Usage (Colab):
    !python change_detection_training/evaluate.py
    !python change_detection_training/evaluate.py --vis-count 8
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch

from change_detection_training.dataset import build_loader
from change_detection_training.model import SiameseChangeDetector
from change_detection_training.utils import ChangeMetrics, load_config, set_seed, visualise_sample


def evaluate(vis_count: int = 4) -> None:
    cfg    = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(cfg["seed"])

    ckpt_path = Path(cfg["checkpoint_dir"]) / "best_model.pth"
    if not ckpt_path.is_file():
        raise FileNotFoundError(
            f"Checkpoint not found: {ckpt_path}\n"
            "Run train.py first to produce best_model.pth."
        )

    # Load checkpoint
    ckpt = torch.load(ckpt_path, map_location=device)
    saved_cfg = ckpt.get("config", cfg)
    image_size = saved_cfg.get("image_size", cfg["image_size"])
    threshold  = saved_cfg.get("threshold",  cfg["threshold"])

    model = SiameseChangeDetector(in_channels=3, base_channels=32).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    print(f"Loaded checkpoint from epoch {ckpt.get('epoch', '?')}  "
          f"(val F1: {ckpt.get('best_f1', 0.0):.4f})")

    # Test DataLoader
    test_loader = build_loader(
        cfg["dataset_root"], "test",
        image_size=image_size,
        batch_size=cfg["batch_size"],
        num_workers=cfg["num_workers"],
        augment=False,
    )
    print(f"Test batches: {len(test_loader)}")

    metrics = ChangeMetrics(threshold=threshold)
    vis_dir = Path(cfg["checkpoint_dir"]) / "test_visuals"
    vis_saved = 0

    with torch.no_grad():
        for batch in test_loader:
            img_a  = batch["image_a"].to(device, non_blocking=True)
            img_b  = batch["image_b"].to(device, non_blocking=True)
            mask   = batch["mask"].to(device, non_blocking=True)
            logits = model(img_a, img_b)
            metrics.update(logits, mask)

            # Save visual panels for the first vis_count samples
            if vis_saved < vis_count:
                for i in range(min(img_a.size(0), vis_count - vis_saved)):
                    fname = batch["filename"][i]
                    save_path = vis_dir / f"{Path(fname).stem}_panel.png"
                    visualise_sample(
                        img_a[i:i+1], img_b[i:i+1],
                        mask[i:i+1],  logits[i:i+1],
                        filename=fname,
                        save_path=save_path,
                    )
                    vis_saved += 1

    m = metrics.compute()
    print("\nTest Results")
    print("------------")
    print(f"Precision : {m['precision']:.4f}")
    print(f"Recall    : {m['recall']:.4f}")
    print(f"F1        : {m['f1']:.4f}")
    print(f"IoU       : {m['iou']:.4f}")
    print(f"\nTP: {m['tp']}  FP: {m['fp']}  FN: {m['fn']}  TN: {m['tn']}")
    if vis_saved:
        print(f"\nVisual panels saved to: {vis_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate LEVIR-CD change detector on test set.")
    parser.add_argument("--vis-count", type=int, default=4, help="Number of visual panels to save.")
    args = parser.parse_args()
    evaluate(vis_count=args.vis_count)

#!/usr/bin/env python
"""Compute validation accuracy for the fine-tuned scene classifier.

Run this in the same Kaggle session right after train/train_convnext.py —
it needs the same GPU/dataset environment and reuses its Dataset/model code.
Not meant to run on a local dev machine.

Usage:
    python run_eval.py \
        --checkpoint /kaggle/working/bentxt_convnext.pt \
        --val-csv /kaggle/working/prepared/val.csv \
        --lmdb /kaggle/input/satqueryai-dataset/BENv2_lithuania_summer.lmdb
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "train"))
from train_convnext import BigEarthPatchDataset, build_model  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--val-csv", required=True)
    parser.add_argument("--lmdb", required=True)
    parser.add_argument("--label-column", default="output")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    import torch
    from torch.utils.data import DataLoader

    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = torch.load(args.checkpoint, map_location=device)
    labels = ckpt["labels"]

    ds = BigEarthPatchDataset(args.val_csv, args.lmdb, labels, args.label_column, ckpt["img_size"])
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=False)

    model = build_model(ckpt["model_name"], len(labels), unfreeze_last_block=False).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    correct = 0
    total = 0
    per_class_correct: Counter = Counter()
    per_class_total: Counter = Counter()
    with torch.no_grad():
        for images, targets in loader:
            images, targets = images.to(device), targets.to(device)
            preds = model(images).argmax(dim=1)
            correct += (preds == targets).sum().item()
            total += targets.size(0)
            for p, t in zip(preds.tolist(), targets.tolist()):
                per_class_total[t] += 1
                if p == t:
                    per_class_correct[t] += 1

    acc = correct / max(total, 1)
    chance = 1.0 / max(len(labels), 1)
    print(f"Validation accuracy: {acc:.4f} over {total} examples ({len(labels)} classes, chance={chance:.4f})")
    print("\nPer-class accuracy:")
    for idx, label in enumerate(labels):
        n = per_class_total.get(idx, 0)
        c = per_class_correct.get(idx, 0)
        if n:
            print(f"  {label:30s} {c}/{n} = {c / n:.3f}")


if __name__ == "__main__":
    main()

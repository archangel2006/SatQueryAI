#!/usr/bin/env python
"""Fine-tune a timm ConvNeXt-tiny scene/land-cover classifier on the prepared
BigEarthNet subset.

DO NOT RUN LOCALLY. This needs a GPU and the dataset (training.csv +
BENv2_lithuania_summer.lmdb), neither of which live in this repo checkout.
Run it on Kaggle with a T4 GPU accelerator — see train/README.md and
train/kaggle_notebook.ipynb for the click-by-click setup. It expects
train.csv / val.csv / labels.json already produced by prepare_dataset.py.

Usage (on Kaggle):
    python train_convnext.py \
        --train-csv /kaggle/working/prepared/train.csv \
        --val-csv /kaggle/working/prepared/val.csv \
        --labels /kaggle/working/prepared/labels.json \
        --lmdb /kaggle/input/satqueryai-dataset/BENv2_lithuania_summer.lmdb \
        --output /kaggle/working/bentxt_convnext.pt \
        --epochs 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bigearthnet_lmdb import load_patch_sample, open_lmdb_env, sample_to_rgb_uint8  # noqa: E402

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class BigEarthPatchDataset:
    def __init__(self, csv_path, lmdb_path, labels, label_column, img_size):
        self.df = pd.read_csv(csv_path)
        self.lmdb_path = lmdb_path
        self._env = None
        self.label_column = label_column
        self.label2idx = {label: i for i, label in enumerate(labels)}
        self.df = self.df[
            self.df[label_column].astype(str).isin(self.label2idx)
        ].reset_index(drop=True)
        self.img_size = img_size

    @property
    def env(self):
        # Opened lazily so each DataLoader worker (forked after __init__) gets its own handle.
        if self._env is None:
            self._env = open_lmdb_env(self.lmdb_path)
        return self._env

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        from torchvision import transforms

        row = self.df.iloc[idx]
        patch_id = row["patch_id"]
        sample = load_patch_sample(self.env, patch_id)
        if sample is None:
            raise KeyError(f"patch_id {patch_id} missing from LMDB")
        rgb = sample_to_rgb_uint8(sample)

        tfm = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize((self.img_size, self.img_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ]
        )
        image = tfm(rgb)
        label = self.label2idx[str(row[self.label_column])]
        return image, label


def build_model(model_name: str, num_classes: int, unfreeze_last_block: bool):
    import timm

    model = timm.create_model(model_name, pretrained=True, num_classes=num_classes)
    for p in model.parameters():
        p.requires_grad = False

    head = getattr(model, "head", None) or getattr(model, "fc", None)
    if head is not None:
        for p in head.parameters():
            p.requires_grad = True

    if unfreeze_last_block:
        stages = getattr(model, "stages", None)
        if stages is not None and len(stages) > 0:
            for p in stages[-1].parameters():
                p.requires_grad = True

    return model


def run_epoch(model, loader, optimizer, device, train: bool):
    import torch
    import torch.nn.functional as F

    model.train(mode=train)
    total_loss, total_correct, total_n = 0.0, 0, 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        with torch.set_grad_enabled(train):
            logits = model(images)
            loss = F.cross_entropy(logits, labels)
            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        total_loss += loss.item() * images.size(0)
        total_correct += (logits.argmax(dim=1) == labels).sum().item()
        total_n += images.size(0)
    return total_loss / max(total_n, 1), total_correct / max(total_n, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--train-csv", required=True)
    parser.add_argument("--val-csv", required=True)
    parser.add_argument("--labels", required=True, help="labels.json from prepare_dataset.py")
    parser.add_argument("--lmdb", required=True)
    parser.add_argument("--label-column", default="output")
    parser.add_argument("--output", required=True, help="Where to save the .pt checkpoint")
    parser.add_argument("--model-name", default="convnext_tiny")
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--unfreeze-last-block", action="store_true")
    args = parser.parse_args()

    import torch
    from torch.utils.data import DataLoader

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    if device == "cpu":
        print("WARNING: no GPU detected. On Kaggle: Settings > Accelerator > GPU T4 x2.")

    labels = json.loads(Path(args.labels).read_text())
    print(f"{len(labels)} classes: {labels}")

    train_ds = BigEarthPatchDataset(args.train_csv, args.lmdb, labels, args.label_column, args.img_size)
    val_ds = BigEarthPatchDataset(args.val_csv, args.lmdb, labels, args.label_column, args.img_size)
    print(f"Train examples: {len(train_ds)}, Val examples: {len(val_ds)}")

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, drop_last=True
    )
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)

    model = build_model(args.model_name, len(labels), args.unfreeze_last_block).to(device)
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.lr)

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = run_epoch(model, train_loader, optimizer, device, train=True)
        val_loss, val_acc = run_epoch(model, val_loader, optimizer, device, train=False)
        print(
            f"epoch {epoch}/{args.epochs}  "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.3f}  "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.3f}  "
            f"({time.time() - t0:.1f}s)"
        )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_name": args.model_name,
            "labels": labels,
            "img_size": args.img_size,
            "mean": IMAGENET_MEAN,
            "std": IMAGENET_STD,
        },
        args.output,
    )
    print(f"Saved checkpoint to {args.output}")


if __name__ == "__main__":
    main()

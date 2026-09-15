from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from training.fusion_model import OpticalSarFusionClassifier
from training.optical_sar_dataset import BigEarthNetFusionDataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a paired S1+S2 BigEarthNet-MM LMDB.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--lmdb", required=True, type=Path)
    parser.add_argument("--split", default="train")
    parser.add_argument("--samples", default=20, type=int)
    parser.add_argument("--batch-size", default=4, type=int)
    args = parser.parse_args()

    dataset = BigEarthNetFusionDataset(args.metadata, args.lmdb, args.split)
    print(f"Split '{args.split}': {len(dataset):,} samples, {len(dataset.label_names)} classes")

    for i in range(min(args.samples, len(dataset))):
        s = dataset[i]
        assert s["optical"].shape[1:] == (120, 120), f"Bad optical shape at {i}: {s['optical'].shape}"
        assert s["sar"].shape[1:] == (120, 120), f"Bad SAR shape at {i}: {s['sar'].shape}"
        assert torch.isfinite(s["optical"]).all() and torch.isfinite(s["sar"]).all(), f"Non-finite tensor at {i}"
        print(i, s["patch_id"], s["optical"].shape, s["sar"].shape)

    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False)
    batch = next(iter(loader))
    model = OpticalSarFusionClassifier(
        optical_channels=batch["optical"].shape[1],
        sar_channels=batch["sar"].shape[1],
        classes=batch["label"].shape[1],
    )
    logits = model(batch["optical"], batch["sar"])
    loss = nn.BCEWithLogitsLoss()(logits, batch["label"])
    assert logits.shape == batch["label"].shape, f"Shape mismatch: {logits.shape} vs {batch['label'].shape}"
    print(f"optical={batch['optical'].shape} sar={batch['sar'].shape} logits={logits.shape} loss={loss.item():.4f}")
    print("Smoke test passed.")


if __name__ == "__main__":
    main()

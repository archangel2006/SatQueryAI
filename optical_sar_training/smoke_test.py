from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from optical_sar_training.fusion_model import OpticalSarFusionClassifier
from optical_sar_training.optical_sar_dataset import BigEarthNetFusionDataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test real BigEarthNet S1/S2 samples.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--lmdb", required=True, type=Path)
    parser.add_argument("--split", default="train")
    parser.add_argument("--samples", default=20, type=int)
    parser.add_argument("--batch-size", default=4, type=int)
    args = parser.parse_args()

    dataset = BigEarthNetFusionDataset(args.metadata, args.lmdb, args.split)
    print(f"Samples in {args.split}: {len(dataset):,}")
    print(f"Classes: {len(dataset.label_names)}")

    for index in range(min(args.samples, len(dataset))):
        sample = dataset[index]
        expected_size = (120, 120)
        if tuple(sample["optical"].shape[1:]) != expected_size:
            raise AssertionError(f"Unexpected optical shape at {index}: {sample['optical'].shape}")
        if tuple(sample["sar"].shape[1:]) != expected_size:
            raise AssertionError(f"Unexpected SAR shape at {index}: {sample['sar'].shape}")
        if not torch.isfinite(sample["optical"]).all() or not torch.isfinite(sample["sar"]).all():
            raise AssertionError(f"Non-finite tensor at sample {index}")
        print(index, sample["patch_id"], sample["optical"].shape, sample["sar"].shape, sample["label"].shape)

    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False)
    batch = next(iter(loader))
    model = OpticalSarFusionClassifier(
        optical_channels=batch["optical"].shape[1],
        sar_channels=batch["sar"].shape[1],
        classes=batch["label"].shape[1],
    )
    logits = model(batch["optical"], batch["sar"])
    loss = nn.BCEWithLogitsLoss()(logits, batch["label"])
    if logits.shape != batch["label"].shape:
        raise AssertionError(f"Logits/target mismatch: {logits.shape} vs {batch['label'].shape}")
    print("Batch optical:", batch["optical"].shape)
    print("Batch SAR:", batch["sar"].shape)
    print("Logits:", logits.shape)
    print("Initial BCEWithLogitsLoss:", loss.detach().item())
    print("Smoke test passed: loader, batch, forward pass, and loss are valid.")


if __name__ == "__main__":
    main()
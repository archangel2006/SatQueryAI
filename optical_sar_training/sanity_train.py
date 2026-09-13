from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from optical_sar_training.fusion_model import OpticalSarFusionClassifier
from optical_sar_training.optical_sar_dataset import BigEarthNetFusionDataset


MAX_TRAIN_PATCHES = 3000
EPOCHS = 5
BATCH_SIZE = 16
LEARNING_RATE = 1e-4


def fusion_collate(batch: list[dict[str, object]]) -> dict[str, torch.Tensor]:
    return {
        "optical": torch.stack([sample["optical"] for sample in batch]),
        "sar": torch.stack([sample["sar"] for sample in batch]),
        "label": torch.stack([sample["label"] for sample in batch]),
    }


def _mean_loss(
    model: OpticalSarFusionClassifier,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    train: bool,
    optimizer: torch.optim.Optimizer | None = None,
) -> float:
    if train:
        model.train()
    else:
        model.eval()

    total_loss = 0.0
    total_samples = 0
    context = torch.enable_grad() if train else torch.no_grad()
    with context:
        for batch in loader:
            optical = batch["optical"].to(device)
            sar = batch["sar"].to(device)
            labels = batch["label"].to(device)
            logits = model(optical, sar)
            loss = criterion(logits, labels)
            if train:
                if optimizer is None:
                    raise ValueError("An optimizer is required for training.")
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
            batch_size = labels.shape[0]
            total_loss += loss.detach().item() * batch_size
            total_samples += batch_size
    return total_loss / max(total_samples, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a two-epoch fusion sanity training pass.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--lmdb", required=True, type=Path)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    torch.manual_seed(0)
    device = torch.device(args.device)
    train_dataset = BigEarthNetFusionDataset(args.metadata, args.lmdb, "train")
    validation_dataset = BigEarthNetFusionDataset(
        args.metadata,
        args.lmdb,
        "val",
        label_names=train_dataset.label_names,
    )
    train_count = min(MAX_TRAIN_PATCHES, len(train_dataset))
    train_subset = Subset(train_dataset, range(train_count))
    train_loader = DataLoader(
        train_subset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=0,
        collate_fn=fusion_collate,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=0,
        collate_fn=fusion_collate,
    )

    first_batch = next(iter(train_loader))
    print(
        "Optical:",
        first_batch["optical"].min().item(),
        first_batch["optical"].max().item(),
        first_batch["optical"].mean().item(),
    )
    print(
        "SAR:",
        first_batch["sar"].min().item(),
        first_batch["sar"].max().item(),
        first_batch["sar"].mean().item(),
    )
    model = OpticalSarFusionClassifier(
        optical_channels=first_batch["optical"].shape[1],
        sar_channels=first_batch["sar"].shape[1],
        classes=first_batch["label"].shape[1],
    ).to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)

    for epoch in range(1, EPOCHS + 1):
        train_loss = _mean_loss(model, train_loader, criterion, device, True, optimizer)
        validation_loss = _mean_loss(model, validation_loader, criterion, device, False)
        print(f"epoch={epoch} train_loss={train_loss:.6f} validation_loss={validation_loss:.6f}")

    checkpoint_path = "/content/drive/MyDrive/SatQueryAI_work/checkpoints/fusion_model.pt"
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "label_names": train_dataset.label_names,
            "optical_channels": first_batch["optical"].shape[1],
            "sar_channels": first_batch["sar"].shape[1],
            "classes": len(train_dataset.label_names),
        },
        checkpoint_path,
    )

    print("Saved checkpoint to:", checkpoint_path)


if __name__ == "__main__":
    main()
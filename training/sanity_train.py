from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from training.fusion_model import OpticalSarFusionClassifier
from training.optical_sar_dataset import BigEarthNetFusionDataset


def _collate(batch: list[dict]) -> dict[str, torch.Tensor]:
    return {
        "optical": torch.stack([s["optical"] for s in batch]),
        "sar": torch.stack([s["sar"] for s in batch]),
        "label": torch.stack([s["label"] for s in batch]),
    }


def _run_epoch(
    model: OpticalSarFusionClassifier,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
) -> float:
    model.train() if optimizer else model.eval()
    total_loss = total_n = 0
    ctx = torch.enable_grad() if optimizer else torch.no_grad()
    with ctx:
        for batch in loader:
            logits = model(batch["optical"].to(device), batch["sar"].to(device))
            loss = criterion(logits, batch["label"].to(device))
            if optimizer:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
            n = batch["label"].shape[0]
            total_loss += loss.detach().item() * n
            total_n += n
    return total_loss / max(total_n, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanity-train the optical-SAR fusion classifier.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--lmdb", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", default=5, type=int)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--max-train-patches", default=3000, type=int)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    torch.manual_seed(0)
    device = torch.device(args.device)

    train_ds = BigEarthNetFusionDataset(args.metadata, args.lmdb, "train")
    val_ds = BigEarthNetFusionDataset(args.metadata, args.lmdb, "val", label_names=train_ds.label_names)
    print(f"train={len(train_ds):,}  val={len(val_ds):,}  classes={len(train_ds.label_names)}")

    train_loader = DataLoader(Subset(train_ds, range(min(args.max_train_patches, len(train_ds)))),
                              batch_size=args.batch_size, shuffle=True, num_workers=0, collate_fn=_collate)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0, collate_fn=_collate)

    first = next(iter(train_loader))
    print(f"optical {tuple(first['optical'].shape)}  sar {tuple(first['sar'].shape)}")

    model = OpticalSarFusionClassifier(
        optical_channels=first["optical"].shape[1],
        sar_channels=first["sar"].shape[1],
        classes=len(train_ds.label_names),
    ).to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)

    for epoch in range(1, args.epochs + 1):
        train_loss = _run_epoch(model, train_loader, criterion, device, optimizer)
        val_loss = _run_epoch(model, val_loader, criterion, device, None)
        print(f"epoch={epoch}  train={train_loss:.4f}  val={val_loss:.4f}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "label_names": train_ds.label_names,
        "optical_channels": first["optical"].shape[1],
        "sar_channels": first["sar"].shape[1],
        "classes": len(train_ds.label_names),
    }, args.output)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()

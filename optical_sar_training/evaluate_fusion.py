from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch
from torch import Tensor
from torch.utils.data import DataLoader

from optical_sar_training.fusion_model import OpticalSarFusionClassifier
from optical_sar_training.optical_sar_dataset import BigEarthNetFusionDataset


def fusion_collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "optical": torch.stack([sample["optical"] for sample in batch]),
        "sar": torch.stack([sample["sar"] for sample in batch]),
        "label": torch.stack([sample["label"] for sample in batch]),
        "contains_cloud_or_shadow": torch.tensor(
            [sample["contains_cloud_or_shadow"] for sample in batch],
            dtype=torch.bool,
        ),
    }


def _confusion_counts(target: Tensor, prediction: Tensor) -> tuple[Tensor, Tensor, Tensor]:
    true_positive = (prediction & target).sum(dim=0).to(torch.float64)
    false_positive = (prediction & ~target).sum(dim=0).to(torch.float64)
    false_negative = (~prediction & target).sum(dim=0).to(torch.float64)
    return true_positive, false_positive, false_negative


def _metrics(target: Tensor, prediction: Tensor) -> dict[str, float]:
    true_positive, false_positive, false_negative = _confusion_counts(target, prediction)
    epsilon = 1e-12
    precision_by_class = true_positive / (true_positive + false_positive).clamp_min(epsilon)
    recall_by_class = true_positive / (true_positive + false_negative).clamp_min(epsilon)
    f1_by_class = (
        2 * precision_by_class * recall_by_class
        / (precision_by_class + recall_by_class).clamp_min(epsilon)
    )
    micro_true_positive = true_positive.sum()
    micro_false_positive = false_positive.sum()
    micro_false_negative = false_negative.sum()
    micro_precision = micro_true_positive / (micro_true_positive + micro_false_positive).clamp_min(epsilon)
    micro_recall = micro_true_positive / (micro_true_positive + micro_false_negative).clamp_min(epsilon)
    micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall).clamp_min(epsilon)
    return {
        "micro_f1": float(micro_f1),
        "macro_f1": float(f1_by_class.mean()),
        "precision": float(micro_precision),
        "recall": float(micro_recall),
    }


def evaluate(
    model: OpticalSarFusionClassifier,
    loader: DataLoader,
    device: torch.device,
    threshold: float,
) -> tuple[dict[str, float], dict[str, float], int]:
    """Evaluate all validation rows and cloudy rows at a sigmoid threshold."""
    model.eval()
    all_targets: list[Tensor] = []
    all_predictions: list[Tensor] = []
    cloud_flags: list[Tensor] = []
    with torch.no_grad():
        for batch in loader:
            logits = model(batch["optical"].to(device), batch["sar"].to(device))
            all_targets.append(batch["label"].to(torch.bool).cpu())
            all_predictions.append((torch.sigmoid(logits).cpu() >= threshold))
            cloud_flags.append(batch["contains_cloud_or_shadow"])
    targets = torch.cat(all_targets)
    predictions = torch.cat(all_predictions)
    clouds = torch.cat(cloud_flags)
    cloudy_metrics = _metrics(targets[clouds], predictions[clouds]) if clouds.any() else {}
    return _metrics(targets, predictions), cloudy_metrics, int(clouds.sum())


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained optical-SAR fusion classifier.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--lmdb", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--threshold", default=0.5, type=float)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()
    if not 0.0 <= args.threshold <= 1.0:
        raise ValueError("--threshold must be between 0 and 1.")

    train_dataset = BigEarthNetFusionDataset(args.metadata, args.lmdb, "train")
    dataset = BigEarthNetFusionDataset(
        args.metadata,
        args.lmdb,
        "val",
        label_names=train_dataset.label_names,
    )
    if "contains_cloud_or_shadow" not in dataset.metadata:
        raise ValueError("Validation metadata must contain contains_cloud_or_shadow.")
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0, collate_fn=fusion_collate)
    first_batch = next(iter(loader))
    model = OpticalSarFusionClassifier(
        optical_channels=first_batch["optical"].shape[1],
        sar_channels=first_batch["sar"].shape[1],
        classes=first_batch["label"].shape[1],
    )
    checkpoint = torch.load(args.checkpoint, map_location=args.device)
    state_dict = checkpoint.get("model_state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
    model.load_state_dict(state_dict)
    model.to(args.device)
    overall, cloudy, cloudy_count = evaluate(model, loader, torch.device(args.device), args.threshold)
    print(f"threshold={args.threshold:.3f} validation_rows={len(dataset)} cloudy_rows={cloudy_count}")
    print("overall", " ".join(f"{key}={value:.6f}" for key, value in overall.items()))
    if cloudy:
        print("cloudy", " ".join(f"{key}={value:.6f}" for key, value in cloudy.items()))
    else:
        print("cloudy no_rows")


if __name__ == "__main__":
    main()
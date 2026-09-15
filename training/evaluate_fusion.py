from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch
from torch import Tensor
from torch.utils.data import DataLoader

from training.fusion_model import OpticalSarFusionClassifier
from training.optical_sar_dataset import BigEarthNetFusionDataset


def _collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "optical": torch.stack([s["optical"] for s in batch]),
        "sar": torch.stack([s["sar"] for s in batch]),
        "label": torch.stack([s["label"] for s in batch]),
        "contains_cloud_or_shadow": torch.tensor([s["contains_cloud_or_shadow"] for s in batch], dtype=torch.bool),
    }


def _metrics(targets: Tensor, preds: Tensor) -> dict[str, float]:
    tp = (preds & targets).sum(0).double()
    fp = (preds & ~targets).sum(0).double()
    fn = (~preds & targets).sum(0).double()
    eps = 1e-12
    per_class_f1 = 2 * tp / (2 * tp + fp + fn + eps)
    micro_tp, micro_fp, micro_fn = tp.sum(), fp.sum(), fn.sum()
    micro_p = micro_tp / (micro_tp + micro_fp + eps)
    micro_r = micro_tp / (micro_tp + micro_fn + eps)
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r + eps)
    return {"micro_f1": float(micro_f1), "macro_f1": float(per_class_f1.mean()),
            "precision": float(micro_p), "recall": float(micro_r)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained optical-SAR fusion classifier.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--lmdb", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--threshold", default=0.5, type=float)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    train_ds = BigEarthNetFusionDataset(args.metadata, args.lmdb, "train")
    val_ds = BigEarthNetFusionDataset(args.metadata, args.lmdb, "val", label_names=train_ds.label_names)
    loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0, collate_fn=_collate)

    first = next(iter(loader))
    model = OpticalSarFusionClassifier(
        optical_channels=first["optical"].shape[1],
        sar_channels=first["sar"].shape[1],
        classes=len(train_ds.label_names),
    )
    ckpt = torch.load(args.checkpoint, map_location=args.device, weights_only=False)
    model.load_state_dict(ckpt.get("model_state_dict", ckpt))
    model.to(args.device).eval()

    all_targets, all_preds, all_clouds = [], [], []
    with torch.no_grad():
        for batch in loader:
            logits = model(batch["optical"].to(args.device), batch["sar"].to(args.device))
            all_targets.append(batch["label"].bool().cpu())
            all_preds.append((torch.sigmoid(logits).cpu() >= args.threshold))
            all_clouds.append(batch["contains_cloud_or_shadow"])

    targets = torch.cat(all_targets)
    preds = torch.cat(all_preds)
    clouds = torch.cat(all_clouds)

    overall = _metrics(targets, preds)
    print(f"val_rows={len(val_ds)}  threshold={args.threshold}")
    print("overall  " + "  ".join(f"{k}={v:.4f}" for k, v in overall.items()))
    if clouds.any():
        cloudy = _metrics(targets[clouds], preds[clouds])
        print(f"cloudy({clouds.sum().item()})  " + "  ".join(f"{k}={v:.4f}" for k, v in cloudy.items()))


if __name__ == "__main__":
    main()

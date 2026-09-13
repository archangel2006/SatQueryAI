"""inference.py — Clean inference API for the trained change detector.

This module is designed to be imported by the backend:

    from change_detection_training.inference import predict_change

It does NOT require ground-truth labels.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchvision.transforms.functional as TF
from PIL import Image
from torch import Tensor

from change_detection_training.model import SiameseChangeDetector

# ImageNet normalisation constants (must match dataset.py)
_MEAN = (0.485, 0.456, 0.406)
_STD  = (0.229, 0.224, 0.225)

# Module-level cache so the model is loaded only once per process.
_model_cache: dict[str, tuple[SiameseChangeDetector, torch.device, dict]] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_model(
    checkpoint_path: str | Path,
    device: torch.device,
) -> tuple[SiameseChangeDetector, dict]:
    """Load (and cache) the model from a checkpoint."""
    key = str(checkpoint_path)
    if key in _model_cache:
        cached_model, cached_device, cfg = _model_cache[key]
        if cached_device == device:
            return cached_model, cfg

    ckpt = torch.load(checkpoint_path, map_location=device)
    cfg  = ckpt.get("config", {})

    model = SiameseChangeDetector(in_channels=3, base_channels=32).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    _model_cache[key] = (model, device, cfg)
    return model, cfg


def _preprocess(
    image: str | Path | np.ndarray | bytes,
    image_size: int,
) -> Tensor:
    """Load and preprocess one image into a [1, 3, H, W] tensor."""
    if isinstance(image, (str, Path)):
        pil = Image.open(image).convert("RGB")
    elif isinstance(image, bytes):
        import io
        pil = Image.open(io.BytesIO(image)).convert("RGB")
    elif isinstance(image, np.ndarray):
        pil = Image.fromarray(
            image if image.dtype == np.uint8 else (image * 255).clip(0, 255).astype(np.uint8)
        ).convert("RGB")
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    pil = TF.resize(pil, [image_size, image_size], interpolation=TF.InterpolationMode.BILINEAR)
    t   = TF.to_tensor(pil)
    t   = TF.normalize(t, _MEAN, _STD)
    return t.unsqueeze(0)   # [1, 3, H, W]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_change(
    image_a: str | Path | np.ndarray | bytes,
    image_b: str | Path | np.ndarray | bytes,
    checkpoint_path: str | Path,
    device: str | torch.device | None = None,
    threshold: float = 0.5,
    image_size: int | None = None,
) -> dict[str, Any]:
    """Run bi-temporal change detection on a pair of images.

    Args:
        image_a:         T1 image — file path, bytes, or numpy array (H×W×3).
        image_b:         T2 image — same format as image_a.
        checkpoint_path: Path to ``best_model.pth``.
        device:          ``"cuda"``, ``"cpu"``, or ``None`` (auto-detect).
        threshold:       Sigmoid threshold for the binary mask.
        image_size:      Override the spatial size from the checkpoint config.

    Returns:
        A dict with:
            ``probability_map`` — float32 numpy array [H, W] in [0, 1].
            ``mask``            — uint8 numpy array [H, W], values 0 or 1.
            ``score``           — float, mean change probability over the image.
            ``changed_pct``     — float, percentage of pixels predicted as changed.
    """
    if device is None:
        resolved_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        resolved_device = torch.device(device)

    model, cfg = _load_model(checkpoint_path, resolved_device)

    size = image_size or cfg.get("image_size", 256)
    thr  = threshold  # caller's threshold takes precedence

    tensor_a = _preprocess(image_a, size).to(resolved_device)
    tensor_b = _preprocess(image_b, size).to(resolved_device)

    with torch.no_grad():
        logits = model(tensor_a, tensor_b)          # [1, 1, H, W]
        prob   = torch.sigmoid(logits)[0, 0]        # [H, W]

    prob_np = prob.cpu().numpy().astype(np.float32)
    mask_np = (prob_np >= thr).astype(np.uint8)

    return {
        "probability_map": prob_np,
        "mask":            mask_np,
        "score":           float(prob_np.mean()),
        "changed_pct":     float(mask_np.mean() * 100.0),
    }


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run change detection on a T1/T2 image pair.")
    parser.add_argument("--image-a",    required=True,  help="Path to T1 image.")
    parser.add_argument("--image-b",    required=True,  help="Path to T2 image.")
    parser.add_argument("--checkpoint", required=True,  help="Path to best_model.pth.")
    parser.add_argument("--threshold",  type=float, default=0.5)
    parser.add_argument("--output",     default=None,   help="Optional path to save the probability map PNG.")
    args = parser.parse_args()

    result = predict_change(
        args.image_a,
        args.image_b,
        args.checkpoint,
        threshold=args.threshold,
    )
    print(f"Score        : {result['score']:.4f}")
    print(f"Changed area : {result['changed_pct']:.2f}%")

    if args.output:
        from PIL import Image as _Image
        prob_uint8 = (result["probability_map"] * 255).astype(np.uint8)
        _Image.fromarray(prob_uint8, mode="L").save(args.output)
        print(f"Probability map saved to: {args.output}")

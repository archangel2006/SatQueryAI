from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.specialists.optical_sar.learned_fusion import LearnedFusion


_learned_fusion: LearnedFusion | None = None


def configure_learned_fusion(checkpoint_path: str, device: str = "cpu") -> LearnedFusion:
    """Load the optional learned fusion checkpoint once for backend inference."""
    global _learned_fusion
    _learned_fusion = LearnedFusion(checkpoint_path, device)
    return _learned_fusion

def _as_hwc(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    if array.ndim == 2:
        return array[..., None]
    if array.ndim != 3:
        raise ValueError("Image data must have two or three dimensions.")
    if array.shape[0] <= 16 and array.shape[-1] > 16:
        return np.moveaxis(array, 0, -1)
    return array


def _read_image(image: bytes | bytearray | np.ndarray) -> np.ndarray:
    if isinstance(image, np.ndarray):
        return _as_hwc(image)
    if not isinstance(image, (bytes, bytearray)):
        raise TypeError("Image input must be bytes or a NumPy array.")

    data = bytes(image)
    try:
        import rasterio
        from rasterio.io import MemoryFile

        with MemoryFile(data) as memory_file:
            with memory_file.open() as dataset:
                return _as_hwc(dataset.read())
    except Exception:
        try:
            with Image.open(io.BytesIO(data)) as image_file:
                return _as_hwc(np.asarray(image_file.convert("RGB")))
        except Exception as exc:  # noqa: BLE001 - normalize decoder errors
            raise ValueError("Could not decode image data.") from exc


def _normalize(array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(array)
    normalized = np.zeros_like(array, dtype=np.float32)
    for channel in range(array.shape[-1]):
        values = array[..., channel]
        valid = finite[..., channel]
        if not np.any(valid):
            continue
        low, high = np.percentile(values[valid], [2, 98])
        if high <= low:
            normalized[..., channel][valid] = 0.5
        else:
            normalized[..., channel][valid] = np.clip(
                (values[valid] - low) / (high - low), 0.0, 1.0
            )
    return normalized, finite.all(axis=-1)


def _overlay_png(
    water_mask: np.ndarray,
    built_up_mask: np.ndarray,
    valid: np.ndarray,
) -> bytes:
    overlay = np.zeros((*valid.shape, 3), dtype=np.uint8)
    overlay[water_mask & valid] = (35, 120, 220)
    overlay[built_up_mask & valid] = (220, 80, 45)
    overlap = water_mask & built_up_mask & valid
    overlay[overlap] = (220, 190, 35)
    image = Image.fromarray(overlay, mode="RGB")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def run_fusion(
    optical: bytes | bytearray | np.ndarray,
    sar: bytes | bytearray | np.ndarray,
    query: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fuse optical and SAR evidence into deterministic masks and statistics.

    This baseline uses independent percentile normalization, optical spectral
    cues, SAR backscatter cues, cloud-aware weighting, and modality agreement.
    It is deliberately model-free so it remains usable when Gemini or a large
    specialist checkpoint is unavailable.
    """
    optical_array = _read_image(optical)
    sar_array = _read_image(sar)
    optical_norm, optical_valid = _normalize(optical_array)
    sar_norm, sar_valid = _normalize(sar_array)

    if optical_norm.shape[:2] != sar_norm.shape[:2]:
        raise ValueError("Optical and SAR images must have matching dimensions.")

    valid = optical_valid & sar_valid
    if not np.any(valid):
        raise ValueError("Optical and SAR images contain no jointly valid pixels.")

    optical_channels = optical_norm.shape[-1]
    optical_mean = optical_norm.mean(axis=-1)
    if optical_channels >= 3:
        red, green, blue = (optical_norm[..., index] for index in range(3))
        water_optical = (blue > red * 0.9) & (blue > green * 0.85) & (optical_mean < 0.65)
        built_up_optical = (optical_mean > 0.58) & ((green - red) < 0.12)
        cloud_mask = (optical_mean > 0.9) & ((optical_norm.max(axis=-1) - optical_norm.min(axis=-1)) < 0.08)
    else:
        water_optical = optical_mean < 0.35
        built_up_optical = optical_mean > 0.65
        cloud_mask = np.zeros_like(optical_mean, dtype=bool)

    sar_backscatter = sar_norm.mean(axis=-1)
    water_sar = sar_backscatter < 0.35
    built_up_sar = sar_backscatter > 0.62

    cloud_pct = float(np.mean(cloud_mask[valid]) * 100.0)
    optical_weight = max(0.2, 1.0 - cloud_pct / 100.0)
    sar_weight = 1.0
    water_score = optical_weight * water_optical.astype(np.float32) + sar_weight * water_sar
    built_up_score = optical_weight * built_up_optical.astype(np.float32) + sar_weight * built_up_sar
    water_mask = (water_score >= (optical_weight + sar_weight) * 0.55) & valid
    built_up_mask = (built_up_score >= (optical_weight + sar_weight) * 0.55) & valid

    water_agreement = np.mean((water_optical == water_sar)[valid])
    built_up_agreement = np.mean((built_up_optical == built_up_sar)[valid])
    modality_agreement = float((water_agreement + built_up_agreement) / 2.0)
    score = float(np.clip(0.65 * modality_agreement + 0.35 * optical_weight, 0.0, 1.0))
    water_pct = float(np.mean(water_mask[valid]) * 100.0)
    built_up_pct = float(np.mean(built_up_mask[valid]) * 100.0)

    learned = _learned_fusion.predict(optical, sar) if _learned_fusion else None

    subject = f" for query '{query.strip()}'" if query and query.strip() else ""
    text = (
        f"Optical and SAR evidence{subject}: approximately {water_pct:.1f}% "
        f"water-like and {built_up_pct:.1f}% built-up-like area. "
        f"Cloud estimate is {cloud_pct:.1f}%; modality agreement is {modality_agreement:.2f}."
    )
    if learned is not None:
        learned_groups = learned["groups"]
        text += (
            f" Learned scene probabilities: water {learned_groups['water']:.2f}, "
            f"built-up {learned_groups['built_up']:.2f}."
        )
        score = float(np.clip((score + max(learned_groups.values())) / 2.0, 0.0, 1.0))
    evidence = {
        "method": "percentile-normalized optical/SAR evidence fusion",
        "shape": list(optical_norm.shape[:2]),
        "water_pct": water_pct,
        "built_up_pct": built_up_pct,
        "optical_weight": optical_weight,
        "sar_weight": sar_weight,
        "modality_agreement": modality_agreement,
        "valid_pct": float(np.mean(valid) * 100.0),
        "metadata": metadata or {},
    }
    if learned is not None:
        evidence["learned_fusion"] = learned
    elif _learned_fusion is not None and _learned_fusion.error:
        evidence["learned_fusion"] = {"available": False, "error": _learned_fusion.error}
    return {
        "text": text,
        "overlay": _overlay_png(water_mask, built_up_mask, valid),
        "cloud_pct": cloud_pct,
        "score": score,
        "evidence": evidence,
    }

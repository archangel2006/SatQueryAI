from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from PIL import Image

from app.specialists.change_detection.learned_change import LearnedChange

logger = logging.getLogger(__name__)


_learned_change: LearnedChange | None = None


def configure_learned_change(checkpoint_path: str, device: str = "cpu") -> LearnedChange:
    """Load the optional learned change checkpoint once at startup."""
    global _learned_change
    _learned_change = LearnedChange(checkpoint_path, device)
    return _learned_change


def _read_image(image: bytes | bytearray | np.ndarray) -> np.ndarray:
    if isinstance(image, np.ndarray):
        array = image.astype(np.float32, copy=False)
        if array.ndim == 2:
            return array[None, ...]
        if array.ndim == 3:
            return array if array.shape[0] <= 16 else np.moveaxis(array, -1, 0)
        raise ValueError("Image data must have two or three dimensions.")
    try:
        import rasterio
        from rasterio.io import MemoryFile

        with MemoryFile(bytes(image)) as memory_file:
            with memory_file.open() as dataset:
                return dataset.read().astype(np.float32)
    except Exception:
        try:
            with Image.open(io.BytesIO(bytes(image))) as image_file:
                return np.moveaxis(np.asarray(image_file.convert("RGB"), dtype=np.float32), -1, 0)
        except Exception as exc:  # noqa: BLE001 - normalize decoder errors
            raise ValueError("Could not decode change-analysis image data.") from exc


def _normalize(array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(array).all(axis=0)
    result = np.zeros_like(array, dtype=np.float32)
    for channel in range(array.shape[0]):
        values = array[channel][np.isfinite(array[channel])]
        if values.size == 0:
            continue
        low, high = np.percentile(values, [2, 98])
        result[channel] = 0.5 if high <= low else np.clip((array[channel] - low) / (high - low), 0.0, 1.0)
    return result, finite


def _components(mask: np.ndarray) -> int:
    remaining = mask.copy()
    count = 0
    height, width = remaining.shape
    for row in range(height):
        for column in range(width):
            if not remaining[row, column]:
                continue
            count += 1
            stack = [(row, column)]
            remaining[row, column] = False
            while stack:
                current_row, current_column = stack.pop()
                for next_row, next_column in (
                    (current_row - 1, current_column),
                    (current_row + 1, current_column),
                    (current_row, current_column - 1),
                    (current_row, current_column + 1),
                ):
                    if 0 <= next_row < height and 0 <= next_column < width and remaining[next_row, next_column]:
                        remaining[next_row, next_column] = False
                        stack.append((next_row, next_column))
    return count


def _overlay_png(mask: np.ndarray) -> bytes:
    overlay = np.zeros((*mask.shape, 4), dtype=np.uint8)
    overlay[mask] = (220, 80, 45, 190)
    output = io.BytesIO()
    Image.fromarray(overlay, mode="RGBA").save(output, format="PNG")
    return output.getvalue()


def run_change(
    t1: bytes | bytearray | np.ndarray,
    t2: bytes | bytearray | np.ndarray,
    query: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run learned change detection when available, then use a deterministic fallback."""
    before, before_valid = _normalize(_read_image(t1))
    after, after_valid = _normalize(_read_image(t2))
    if before.shape[1:] != after.shape[1:]:
        raise ValueError("Before and after images must have matching dimensions.")
    valid = before_valid & after_valid
    if not np.any(valid):
        raise ValueError("Before and after images contain no jointly valid pixels.")

    # Pass raw inputs to the learned model so it can apply its own preprocessing.
    learned_probability = _learned_change.predict(t1, t2) if _learned_change else None
    if learned_probability is not None:
        logger.info("[change] SiameseChangeDetector ran — learned model active")
    else:
        logger.info("[change] Fallback pixel-difference ran — model unavailable")
    if learned_probability is not None:
        difference = learned_probability
        learned_valid = np.ones_like(difference, dtype=bool)
        threshold = 0.5
        changed = difference >= threshold
        method = "learned_change"
        valid_for_stats = learned_valid
    else:
        difference = np.mean(np.abs(after - before), axis=0)
        valid_difference = difference[valid]
        threshold = float(np.percentile(valid_difference, 90))
        changed = (difference >= threshold) & valid if threshold > 0 else np.zeros_like(valid)
        method = "normalized_pixel_difference"
        valid_for_stats = valid
    valid_difference = difference[valid_for_stats]
    change_pct = float(np.mean(changed[valid_for_stats]) * 100.0)
    mean_difference = float(np.mean(valid_difference))
    score = float(np.clip((threshold / (mean_difference + 1e-6)) / 3.0, 0.0, 1.0))
    evidence = {
        "method": method,
        "shape": list(difference.shape),
        "valid_pct": float(np.mean(valid_for_stats) * 100.0),
        "changed_pixels": int(changed.sum()),
        "changed_regions": _components(changed),
        "threshold": threshold,
        "mean_difference": mean_difference,
        "percentile_difference": float(np.percentile(valid_difference, 90)),
        "metadata": {
            "fallback": learned_probability is None,
            **(metadata or {}),
        },
    }
    subject = f" for query '{query.strip()}'" if query and query.strip() else ""
    text = (
        f"Change analysis{subject}: approximately {change_pct:.1f}% of valid pixels "
        f"changed across {evidence['changed_regions']} connected region(s)."
    )
    return {
        "text": text,
        "overlay": _overlay_png(changed),
        "score": score,
        "change_pct": change_pct,
        "evidence": evidence,
    }

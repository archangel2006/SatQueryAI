"""Shared helpers for reading BigEarthNet-v2 patch tensors out of the
BENv2_lithuania_summer.lmdb store used by this project.

Imported by prepare_dataset.py, train_convnext.py, run_eval.py and
train_lora.py. None of those scripts are meant to run on a local dev
machine — the dataset lives on Kaggle (or wherever training.csv +
BENv2_lithuania_summer.lmdb are attached). See train/README.md.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Sentinel-2 true-color bands in the reBEN / BigEarthNet-v2 safetensors sample
# (B04=red, B03=green, B02=blue). Sentinel-1 fallback is VV.
# If your LMDB uses different keys, run `prepare_dataset.py --inspect-only`
# first (it prints the keys of one decoded sample) and update these constants.
S2_RED, S2_GREEN, S2_BLUE = "B04", "B03", "B02"
S1_PRIMARY = "VV"


def open_lmdb_env(lmdb_path: str):
    import lmdb

    return lmdb.open(
        lmdb_path,
        readonly=True,
        lock=False,
        readahead=False,
        max_readers=126,
    )


def load_patch_sample(env, patch_id: str) -> Optional[dict]:
    """Fetch and decode the safetensors payload for one patch_id, or None if missing."""
    from safetensors.numpy import load as safetensor_load

    with env.begin(write=False) as txn:
        raw = txn.get(str(patch_id).encode())
    if raw is None:
        return None
    return safetensor_load(raw)


def _percentile_stretch(band: np.ndarray, lo: float = 2.0, hi: float = 98.0) -> np.ndarray:
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros_like(band, dtype=np.uint8)
    p_lo, p_hi = np.percentile(finite, [lo, hi])
    if p_hi <= p_lo:
        return np.zeros_like(band, dtype=np.uint8)
    scaled = np.clip((band - p_lo) / (p_hi - p_lo), 0, 1)
    return (scaled * 255).astype(np.uint8)


def sample_to_rgb_uint8(sample: dict) -> np.ndarray:
    """Best-effort conversion of a BigEarthNet-v2 patch sample dict to an HxWx3 uint8 RGB image."""
    keys = set(sample.keys())
    if {S2_RED, S2_GREEN, S2_BLUE} <= keys:
        r = _percentile_stretch(np.asarray(sample[S2_RED]).astype(np.float64))
        g = _percentile_stretch(np.asarray(sample[S2_GREEN]).astype(np.float64))
        b = _percentile_stretch(np.asarray(sample[S2_BLUE]).astype(np.float64))
        return np.stack([r, g, b], axis=-1)

    if S1_PRIMARY in keys:
        gray = _percentile_stretch(np.asarray(sample[S1_PRIMARY]).astype(np.float64))
        return np.stack([gray, gray, gray], axis=-1)

    first_key = sorted(keys)[0]
    logger.warning(
        "Unrecognized band keys %s; falling back to first array '%s'. "
        "Update S2_RED/S2_GREEN/S2_BLUE/S1_PRIMARY in bigearthnet_lmdb.py if this is wrong.",
        keys,
        first_key,
    )
    arr = np.asarray(sample[first_key])
    gray = _percentile_stretch(arr.astype(np.float64))
    return np.stack([gray, gray, gray], axis=-1)

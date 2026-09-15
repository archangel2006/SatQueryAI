from __future__ import annotations

import numpy as np
import pytest

from app.specialists.optical_sar.fusion import run_fusion


def test_run_fusion_returns_evidence_and_overlay() -> None:
    optical = np.zeros((12, 10, 3), dtype=np.float32)
    optical[..., 2] = 1.0
    sar = np.zeros((12, 10), dtype=np.float32)

    result = run_fusion(optical, sar, metadata={"optical": "scene.tif"})

    assert set(result) == {"text", "overlay", "cloud_pct", "score", "evidence"}
    assert result["overlay"][:8] == b"\x89PNG\r\n\x1a\n"
    assert 0.0 <= result["score"] <= 1.0
    assert result["evidence"]["shape"] == [12, 10]
    assert result["evidence"]["metadata"] == {"optical": "scene.tif"}


def test_run_fusion_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="matching dimensions"):
        run_fusion(
            np.zeros((8, 8, 3), dtype=np.float32),
            np.zeros((7, 8), dtype=np.float32),
        )


def test_run_fusion_rejects_no_jointly_valid_pixels() -> None:
    invalid = np.full((4, 4), np.nan, dtype=np.float32)

    with pytest.raises(ValueError, match="no jointly valid pixels"):
        run_fusion(invalid, invalid)
from __future__ import annotations

import base64

import numpy as np
import pytest

from app.specialists.change_detection.change import run_change


def test_identical_arrays_have_no_change() -> None:
    image = np.ones((3, 12, 12), dtype=np.float32)
    result = run_change(image, image)
    assert result["change_pct"] == 0.0
    assert result["evidence"]["changed_regions"] == 0


def test_changed_region_returns_overlay_and_statistics() -> None:
    before = np.zeros((3, 12, 12), dtype=np.float32)
    after = before.copy()
    after[:, 3:9, 4:10] = 1.0
    result = run_change(before, after)
    assert 0.0 <= result["change_pct"] <= 100.0
    assert result["evidence"]["changed_pixels"] > 0
    assert base64.b64encode(result["overlay"]).startswith(b"iVBOR")


def test_change_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="matching dimensions"):
        run_change(np.zeros((3, 8, 8)), np.zeros((3, 7, 8)))
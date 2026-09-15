from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.compatibility.checker import check_compatibility
from app.main import app

client = TestClient(app)


def test_ask_scene_requires_one_file() -> None:
    result = check_compatibility("ask_scene", [])
    assert result.valid is False
    assert result.error is not None


def test_ask_scene_accepts_png(sample_png_bytes: bytes) -> None:
    result = check_compatibility("ask_scene", [("bench.png", sample_png_bytes)])
    assert result.valid is True
    assert result.metadata is not None
    assert result.extras.get("note")


def test_ask_scene_accepts_geotiff(sample_geotiff_bytes: bytes) -> None:
    result = check_compatibility("ask_scene", [("scene.tif", sample_geotiff_bytes)])
    assert result.valid is True
    assert result.metadata is not None
    assert result.metadata.format_kind == "geotiff"


def test_compatibility_endpoint_png(sample_png_bytes: bytes) -> None:
    res = client.post(
        "/compatibility",
        data={"job": "ask_scene"},
        files={"file": ("bench.png", sample_png_bytes, "image/png")},
    )
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_compatibility_endpoint_missing_file() -> None:
    res = client.post(
        "/compatibility",
        data={"job": "ask_scene"},
    )
    assert res.status_code == 200
    assert res.json()["valid"] is False


def test_optical_sar_accepts_matching_pair(
    sample_geotiff_bytes: bytes, sample_sar_geotiff_bytes: bytes
) -> None:
    result = check_compatibility(
        "optical_sar",
        [
            ("optical.tif", sample_geotiff_bytes),
            ("radar.tif", sample_sar_geotiff_bytes),
        ],
    )

    assert result.valid is True
    assert result.metadata is not None
    assert result.metadata.modality_guess == "optical"
    assert result.extras["modalities"] == ["optical", "sar"]


def test_optical_sar_accepts_explicit_upload_order(
    sample_sar_geotiff_bytes: bytes,
) -> None:
    result = check_compatibility(
        "optical_sar",
        [
            ("optical-slot.tif", sample_sar_geotiff_bytes),
            ("sar-slot.tif", sample_sar_geotiff_bytes),
        ],
        ordered_modalities=True,
    )

    assert result.valid is True
    assert result.extras["modalities"] == ["optical", "sar"]
    assert result.extras["detected_modalities"] == ["sar", "sar"]


def test_optical_sar_requires_two_images() -> None:
    result = check_compatibility("optical_sar", [])

    assert result.valid is False
    assert "exactly two" in (result.error or "")


def test_optical_sar_rejects_two_optical_images(sample_geotiff_bytes: bytes) -> None:
    result = check_compatibility(
        "optical_sar",
        [("first.tif", sample_geotiff_bytes), ("second.tif", sample_geotiff_bytes)],
    )

    assert result.valid is False
    assert "one optical image and one SAR image" in (result.error or "")


def test_optical_sar_rejects_mismatched_dimensions(
    sample_png_bytes: bytes, sample_sar_geotiff_bytes: bytes
) -> None:
    result = check_compatibility(
        "optical_sar",
        [("optical.png", sample_png_bytes), ("radar.tif", sample_sar_geotiff_bytes)],
    )

    assert result.valid is False
    assert "matching dimensions" in (result.error or "")


def test_optical_sar_endpoint_accepts_repeated_files(
    sample_geotiff_bytes: bytes, sample_sar_geotiff_bytes: bytes
) -> None:
    res = client.post(
        "/compatibility",
        data={"job": "optical_sar"},
        files=[
            ("files", ("optical.tif", sample_geotiff_bytes, "image/tiff")),
            ("files", ("radar.tif", sample_sar_geotiff_bytes, "image/tiff")),
        ],
    )

    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_fusion_endpoint_returns_specialist_result(
    client: TestClient, sample_geotiff_bytes: bytes, sample_sar_geotiff_bytes: bytes
) -> None:
    res = client.post(
        "/fusion",
        data={"query": "identify water and built-up regions"},
        files=[
            ("files", ("optical.tif", sample_geotiff_bytes, "image/tiff")),
            ("files", ("radar.tif", sample_sar_geotiff_bytes, "image/tiff")),
        ],
    )

    assert res.status_code == 200
    body = res.json()
    assert body["text"]
    assert 0.0 <= body["score"] <= 1.0
    assert base64.b64decode(body["overlay_png_base64"])[:8] == b"\x89PNG\r\n\x1a\n"
    assert body["evidence"]["method"]
    assert body["evidence"]["llm_wording"]["used"] is False


def test_fusion_endpoint_rejects_incomplete_pair(
    sample_geotiff_bytes: bytes,
) -> None:
    res = client.post(
        "/fusion",
        files=[("files", ("optical.tif", sample_geotiff_bytes, "image/tiff"))],
    )

    assert res.status_code == 400
    assert "exactly two" in res.json()["detail"]


def test_before_after_compatibility_requires_two_images() -> None:
    result = check_compatibility("before_after", [])
    assert result.valid is False
    assert "exactly two" in (result.error or "")

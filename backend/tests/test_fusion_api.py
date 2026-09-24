from __future__ import annotations

import io

import numpy as np
from rasterio.transform import from_origin


def _geotiff_bytes(*, bands: int, dtype: str, height: int = 32, width: int = 32) -> bytes:
    import rasterio

    data = np.zeros((bands, height, width), dtype=dtype)
    if bands >= 3:
        data[0] = 400
        data[1] = 500
        data[2] = 900
    else:
        data[0] = 0.08
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=bands,
        dtype=dtype,
        crs="EPSG:4326",
        transform=from_origin(77.0, 29.0, 0.001, 0.001),
    ) as dst:
        dst.write(data)
    return buf.getvalue()


def test_fusion_endpoint_returns_overlay(client) -> None:
    optical = _geotiff_bytes(bands=3, dtype="float32")
    sar = _geotiff_bytes(bands=1, dtype="float32")
    response = client.post(
        "/fusion",
        data={"query": "Identify water and built-up regions using both images."},
        files=[
            ("files", ("optical.tif", optical, "image/tiff")),
            ("files", ("sar.tif", sar, "image/tiff")),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"]
    assert body["overlay_png_base64"]
    assert "water_pct" in body["evidence"]
    assert "built_up_pct" in body["evidence"]


def test_fusion_rejects_mismatched_sizes(client) -> None:
    optical = _geotiff_bytes(bands=3, dtype="float32", height=32, width=32)
    sar = _geotiff_bytes(bands=1, dtype="float32", height=16, width=16)
    response = client.post(
        "/fusion",
        files=[
            ("files", ("optical.tif", optical, "image/tiff")),
            ("files", ("sar.tif", sar, "image/tiff")),
        ],
    )
    assert response.status_code == 400
    assert "matching dimensions" in response.json()["detail"].lower()

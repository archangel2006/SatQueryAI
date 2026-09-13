from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas import FormatKind, ImageMetadata, ModalityGuess

GEOTIFF_EXTS = {".tif", ".tiff"}
RASTER_EXTS = {".png", ".jpg", ".jpeg"}
ALLOWED_EXTS = GEOTIFF_EXTS | RASTER_EXTS
MAX_UPLOAD_BYTES = 80 * 1024 * 1024


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed_filename(filename: str) -> bool:
    return extension_of(filename) in ALLOWED_EXTS


def _percentile_stretch(band: np.ndarray, lo: float = 2.0, hi: float = 98.0) -> np.ndarray:
    finite = band[np.isfinite(band)]
    if finite.size == 0:
        return np.zeros_like(band, dtype=np.uint8)
    p_lo, p_hi = np.percentile(finite, [lo, hi])
    if p_hi <= p_lo:
        return np.zeros_like(band, dtype=np.uint8)
    scaled = (band - p_lo) / (p_hi - p_lo)
    scaled = np.clip(scaled, 0, 1)
    return (scaled * 255).astype(np.uint8)


def _sar_log_preview(band: np.ndarray) -> np.ndarray:
    eps = 1e-6
    log = 10.0 * np.log10(np.maximum(band.astype(np.float64), 0) + eps)
    return _percentile_stretch(log)


def _guess_modality(
    band_count: int,
    dtype: np.dtype,
    filename: str = "",
    descriptions: tuple[str | None, ...] = (),
) -> ModalityGuess:
    identifiers = " ".join(
        [filename.lower(), *(description or "" for description in descriptions)]
    )
    if any(
        token in identifiers
        for token in ("sar", "radar", "sentinel-1", "sentinel1", "risat", "vv", "vh")
    ):
        return "sar"
    if band_count == 1 and np.issubdtype(dtype, np.floating):
        return "sar"
    if band_count >= 3:
        return "optical"
    if band_count in (1, 2):
        return "sar"
    return "unknown"


def _png_base64(rgb: np.ndarray) -> str:
    if rgb.ndim == 2:
        img = Image.fromarray(rgb, mode="L").convert("RGB")
    else:
        img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def preview_from_bytes(data: bytes, filename: str) -> tuple[str, ImageMetadata]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File too large (max 80 MB).")
    if not is_allowed_filename(filename):
        raise ValueError(
            "Unsupported file type. Use GeoTIFF (.tif/.tiff), or PNG/JPEG for benchmark images."
        )

    ext = extension_of(filename)
    if ext in RASTER_EXTS:
        return _preview_pillow(data, filename)
    return _preview_rasterio(data, filename)


def _preview_pillow(data: bytes, filename: str) -> tuple[str, ImageMetadata]:
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    arr = np.asarray(img)
    h, w = arr.shape[0], arr.shape[1]
    meta = ImageMetadata(
        width=w,
        height=h,
        band_count=3,
        crs=None,
        bounds=None,
        modality_guess="optical",
        format_kind="raster",
        filename=filename,
    )
    return _png_base64(arr), meta


def _preview_rasterio(data: bytes, filename: str) -> tuple[str, ImageMetadata]:
    import rasterio
    from rasterio.io import MemoryFile

    with MemoryFile(data) as mem:
        with mem.open() as ds:
            count = ds.count
            height, width = ds.height, ds.width
            crs = str(ds.crs) if ds.crs else None
            bounds = None
            if ds.crs is not None:
                b = ds.bounds
                bounds = [float(b.left), float(b.bottom), float(b.right), float(b.top)]

            # Downsample large rasters for preview
            max_side = 1024
            scale = max(height / max_side, width / max_side, 1.0)
            out_h = max(1, int(height / scale))
            out_w = max(1, int(width / scale))

            modality = _guess_modality(
                count,
                ds.dtypes[0] if count else np.dtype("float32"),
                filename,
                tuple(ds.descriptions or ()),
            )

            if count >= 3 and modality != "sar":
                # Prefer RGB-ish first three bands
                bands = []
                for i in range(1, 4):
                    band = ds.read(i, out_shape=(out_h, out_w), resampling=rasterio.enums.Resampling.bilinear)
                    bands.append(_percentile_stretch(band.astype(np.float64)))
                rgb = np.stack(bands, axis=-1)
                modality = "optical"
            else:
                band = ds.read(1, out_shape=(out_h, out_w), resampling=rasterio.enums.Resampling.bilinear)
                gray = _sar_log_preview(band) if modality == "sar" else _percentile_stretch(band.astype(np.float64))
                rgb = np.stack([gray, gray, gray], axis=-1)

            format_kind: FormatKind = "geotiff"
            meta = ImageMetadata(
                width=width,
                height=height,
                band_count=count,
                crs=crs,
                bounds=bounds,
                modality_guess=modality,
                format_kind=format_kind,
                filename=filename,
            )
            return _png_base64(rgb), meta

from __future__ import annotations

import io
import os

# Must set before app imports create the engine.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["GCS_BUCKET"] = ""
os.environ["GOOGLE_CLOUD_PROJECT"] = ""
os.environ["CLERK_JWKS_URL"] = ""
os.environ["CLERK_ISSUER"] = ""
# Do not load 100MB+ checkpoints during pytest.
os.environ["CHANGE_CHECKPOINT_PATH"] = ""
os.environ["FUSION_CHECKPOINT_PATH"] = ""
os.environ["LOCAL_CLASSIFIER_PATH"] = "__no_classifier__.pt"
# Never hit the live Colab/ngrok VLM or ElevenLabs during pytest.
os.environ["SATQUERY_VLM_URL"] = ""
os.environ["ELEVENLABS_API_KEY"] = ""
os.environ["ELEVENLABS_VOICE_ID"] = ""

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.auth.clerk import AuthUser, get_current_user
from app.config import get_settings
from app.llm.gemini import FakeLLM, set_llm
from app.main import app
from app.storage.gcs import MemoryStorage, set_storage

get_settings.cache_clear()


@pytest.fixture
def sample_png_bytes() -> bytes:
    img = Image.new("RGB", (32, 24), color=(20, 80, 140))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_geotiff_bytes() -> bytes:
    import rasterio
    from rasterio.transform import from_origin

    height, width = 48, 64
    data = np.zeros((3, height, width), dtype=np.float32)
    data[0] = np.linspace(100, 2000, width, dtype=np.float32)
    data[1] = np.linspace(200, 1800, width, dtype=np.float32)
    data[2] = np.linspace(50, 1500, width, dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    data[0] += xx * 10
    data[1] += yy * 10

    transform = from_origin(77.0, 29.0, 0.001, 0.001)
    buf = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 3,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(data)
    return buf.getvalue()


@pytest.fixture
def sample_sar_geotiff_bytes() -> bytes:
    import rasterio
    from rasterio.transform import from_origin

    height, width = 48, 64
    yy, xx = np.mgrid[0:height, 0:width]
    data = (0.1 + (xx + yy) / 1000).astype(np.float32)[None, ...]
    transform = from_origin(77.0, 29.0, 0.001, 0.001)
    buf = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(data)
    return buf.getvalue()


@pytest.fixture
def sample_dual_polarization_sar_geotiff_bytes() -> bytes:
    import rasterio
    from rasterio.transform import from_origin

    height, width = 48, 64
    yy, xx = np.mgrid[0:height, 0:width]
    data = np.stack(
        [0.1 + (xx + yy) / 1000, 0.2 + (xx * 2 + yy) / 1000],
        axis=0,
    ).astype(np.float32)
    transform = from_origin(77.0, 29.0, 0.001, 0.001)
    buf = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 2,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(data)
        dst.set_band_description(1, "VV")
        dst.set_band_description(2, "VH")
    return buf.getvalue()


@pytest.fixture
def sample_multiband_sar_geotiff_bytes() -> bytes:
    import rasterio
    from rasterio.transform import from_origin

    height, width = 24, 32
    yy, xx = np.mgrid[0:height, 0:width]
    data = np.stack(
        [0.1 + (xx + yy) / 1000, 0.2 + (xx * 2 + yy) / 1000, 0.3 + yy / 1000],
        axis=0,
    ).astype(np.float32)
    buf = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 3,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(77.0, 29.0, 0.001, 0.001),
    }
    with rasterio.open(buf, "w", **profile) as dst:
        dst.write(data)
        dst.set_band_description(1, "VV")
        dst.set_band_description(2, "VH")
        dst.set_band_description(3, "incidence angle")
    return buf.getvalue()


@pytest.fixture
def memory_storage() -> MemoryStorage:
    store = MemoryStorage()
    set_storage(store)
    set_llm(FakeLLM())
    yield store
    set_storage(None)
    set_llm(None)


def _override_user(user_id: str):
    async def _dep() -> AuthUser:
        return AuthUser(clerk_user_id=user_id)

    return _dep


@pytest.fixture
def client(memory_storage: MemoryStorage):
    app.dependency_overrides[get_current_user] = _override_user("user_a")
    with TestClient(app) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def other_client(memory_storage: MemoryStorage):
    app.dependency_overrides[get_current_user] = _override_user("user_b")
    with TestClient(app) as ac:
        yield ac
    app.dependency_overrides.clear()

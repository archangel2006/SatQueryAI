from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np

# ImageNet normalisation constants — must match change_detection_training/dataset.py
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class LearnedChange:
    """Adapter that loads a SiameseChangeDetector checkpoint (best_model.pth)
    trained by change_detection_training/train.py on LEVIR-CD.

    Inputs to predict() are raw RGB byte payloads (PNG / GeoTIFF).
    The adapter handles decoding, resizing, and ImageNet normalisation
    internally so change.py does not need to change.
    """

    def __init__(self, checkpoint_path: str, device: str = "cpu") -> None:
        self.checkpoint_path = checkpoint_path
        self.device_name = device
        self.model: Any = None
        self.device: Any = None
        self.image_size: int = 256
        self.error: str | None = None
        self._load()

    @property
    def available(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        if not self.checkpoint_path or not Path(self.checkpoint_path).is_file():
            self.error = "Change checkpoint path is not configured or does not exist."
            return
        try:
            import torch
            from change_detection_training.model import SiameseChangeDetector

            checkpoint = torch.load(self.checkpoint_path, map_location=self.device_name, weights_only=False)
            cfg = checkpoint.get("config", {})
            self.image_size = int(cfg.get("image_size", 256))

            self.device = torch.device(self.device_name)
            self.model = SiameseChangeDetector(in_channels=3, base_channels=32)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.to(self.device).eval()
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            self.model = None
            self.error = f"Could not load SiameseChangeDetector checkpoint: {exc}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decode_to_rgb_array(self, image: bytes | bytearray | np.ndarray) -> np.ndarray:
        """Return a float32 HWC array in [0, 1] from any supported input."""
        if isinstance(image, np.ndarray):
            arr = image.astype(np.float32, copy=False)
            # Accept CHW (from change.py's _read_image) or HWC
            if arr.ndim == 3 and arr.shape[0] <= 4:
                arr = np.moveaxis(arr, 0, -1)   # CHW → HWC
            # Keep only first 3 channels
            arr = arr[..., :3]
            # Rescale to [0, 1] if values look like uint8
            if arr.max() > 1.0:
                arr = arr / 255.0
            return arr.astype(np.float32)

        raw = bytes(image)
        # Try PIL (PNG / JPEG / GeoTIFF via GDAL-backed PIL)
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as pil:
                arr = np.asarray(pil.convert("RGB"), dtype=np.float32) / 255.0
            return arr
        except Exception:  # noqa: BLE001
            pass
        # Try rasterio for multi-band GeoTIFF
        try:
            import rasterio
            from rasterio.io import MemoryFile
            with MemoryFile(raw) as mf:
                with mf.open() as ds:
                    bands = ds.read(list(range(1, min(4, ds.count + 1)))).astype(np.float32)
            # bands is CHW; take first 3 and move to HWC
            arr = np.moveaxis(bands[:3], 0, -1)
            if arr.max() > 1.0:
                arr = arr / arr.max()
            return arr
        except Exception as exc:  # noqa: BLE001
            raise ValueError("LearnedChange: could not decode image bytes.") from exc

    def _preprocess(self, image: bytes | bytearray | np.ndarray) -> Any:
        """Decode → resize → normalise → return [1, 3, H, W] tensor."""
        import torch
        import torch.nn.functional as F
        from PIL import Image

        arr = self._decode_to_rgb_array(image)   # HWC float32 [0,1]
        # Normalise with ImageNet stats
        arr = (arr - _MEAN) / _STD
        # HWC → CHW → [1, C, H, W]
        tensor = torch.from_numpy(np.moveaxis(arr, -1, 0)).unsqueeze(0).float()
        # Resize to training resolution
        tensor = F.interpolate(
            tensor, size=(self.image_size, self.image_size),
            mode="bilinear", align_corners=False,
        )
        return tensor.to(self.device)

    # ------------------------------------------------------------------
    # Public API consumed by change.py
    # ------------------------------------------------------------------

    def predict(self, before: bytes | bytearray | np.ndarray,
                after:  bytes | bytearray | np.ndarray) -> np.ndarray | None:
        """Return a float32 [H, W] probability map in [0, 1], or None on failure."""
        if not self.available:
            return None
        try:
            import torch
            tensor_a = self._preprocess(before)
            tensor_b = self._preprocess(after)
            with torch.inference_mode():
                logits = self.model(tensor_a, tensor_b)          # [1, 1, H, W]
                prob   = torch.sigmoid(logits)[0, 0].cpu().numpy()
            return np.asarray(prob, dtype=np.float32)
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            self.error = f"SiameseChangeDetector inference failed: {exc}"
            return None

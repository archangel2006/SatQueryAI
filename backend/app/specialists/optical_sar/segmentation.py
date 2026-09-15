"""Adapter for the S1S2-Water `OpticalSarFusionSegmenter` deployment checkpoint.

This is intentionally separate from ``learned_fusion.py``: that module supports
the legacy scene-classification checkpoint, while this adapter produces a dense
binary water mask from real Sentinel-1 VV/VH and six-band Sentinel-2 imagery.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np


# The backend is normally launched from backend/, so expose the workspace root
# containing the sibling training package without changing the old classifier.
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

FINAL_SCENES = {"1", "5", "6", "7", "8"}


class WaterSegmentationAdapter:
    """Optional, checkpoint-backed S1/S2 water segmentation inference adapter."""

    def __init__(self, checkpoint_path: str, device: str = "cpu") -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.device_name = device
        self.device: Any = None
        self.model: Any = None
        self.normalization_config: Any = None
        self.error: str | None = None
        self.metadata: dict[str, Any] = {}
        self._load()

    @property
    def available(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        if not self.checkpoint_path.is_file():
            self.error = "Water-segmentation checkpoint path is not configured or does not exist."
            return
        try:
            import torch
            from training.fusion_model import OpticalSarFusionSegmenter
            from training.s1s2_water_dataset import NormalizationConfig

            checkpoint = torch.load(self.checkpoint_path, map_location="cpu", weights_only=False)
            self._validate_final_checkpoint(checkpoint)
            model_config = checkpoint.get("model_config")
            if not isinstance(model_config, dict):
                raise ValueError("Checkpoint lacks model_config; it is not a deployable final segmentation checkpoint.")
            self.normalization_config = NormalizationConfig.from_dict(
                checkpoint.get("normalization_config", {})
            )
            self.device = torch.device(self.device_name)
            if self.device.type == "cuda" and not torch.cuda.is_available():
                raise ValueError("CUDA was configured for water segmentation but is unavailable.")
            self.model = OpticalSarFusionSegmenter(**model_config).to(self.device)
            self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
            self.model.eval()
            self.metadata = {
                "scene_ids": checkpoint.get("scene_ids"),
                "train_scenes": checkpoint.get("train_scenes"),
                "training_mode": checkpoint.get("training_mode"),
                "loss_configuration": checkpoint.get("loss_configuration"),
                "parameter_count": checkpoint.get("parameter_count"),
            }
        except Exception as exc:  # noqa: BLE001 - optional deployment capability
            self.model = None
            self.error = f"Could not load water-segmentation checkpoint: {exc}"

    @staticmethod
    def _validate_final_checkpoint(checkpoint: dict[str, Any]) -> None:
        """Reject held-out folds and stale baseline checkpoints from deployment."""
        scene_ids = {str(value) for value in checkpoint.get("scene_ids", [])}
        train_scenes = {str(value) for value in checkpoint.get("train_scenes", [])}
        val_scenes = checkpoint.get("val_scenes", [])
        mode = checkpoint.get("training_mode")
        if (
            scene_ids != FINAL_SCENES
            or train_scenes != FINAL_SCENES
            or val_scenes not in ([], None)
            or mode != "final_all_scenes_no_heldout_validation"
        ):
            raise ValueError(
                "Checkpoint metadata is not a final all-five-scenes deployment model. "
                "Expected scene_ids/train_scenes {1,5,6,7,8}, empty val_scenes, and "
                "training_mode='final_all_scenes_no_heldout_validation'."
            )

    @staticmethod
    def _read_raster(data: bytes, expected_bands: int, band_names: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray, Any, Any]:
        import rasterio
        from rasterio.io import MemoryFile

        with MemoryFile(data) as memory_file:
            with memory_file.open() as src:
                if src.count < expected_bands:
                    raise ValueError(f"Raster has {src.count} band(s); expected at least {expected_bands}.")
                descriptions = tuple((item or "").strip().lower() for item in src.descriptions)
                indexes: list[int] = []
                for position, name in enumerate(band_names, start=1):
                    match = next((i for i, value in enumerate(descriptions, start=1) if value == name.lower()), None)
                    indexes.append(match or position)
                image = src.read(indexes).astype(np.float32)
                valid = np.isfinite(image).all(axis=0)
                if src.nodata is not None and np.isfinite(src.nodata):
                    valid &= np.all(image != src.nodata, axis=0)
                return image, valid, src.transform, src.crs

    @staticmethod
    def _align_s1_to_s2(
        s1: np.ndarray, s1_valid: np.ndarray, s1_transform: Any, s1_crs: Any,
        s2_shape: tuple[int, int], s2_transform: Any, s2_crs: Any,
    ) -> tuple[np.ndarray, np.ndarray]:
        from rasterio.enums import Resampling
        from rasterio.warp import reproject

        aligned = np.zeros((2, *s2_shape), dtype=np.float32)
        for band in range(2):
            reproject(
                s1[band], aligned[band], src_transform=s1_transform, src_crs=s1_crs,
                dst_transform=s2_transform, dst_crs=s2_crs, resampling=Resampling.bilinear,
            )
        aligned_valid = np.zeros(s2_shape, dtype=np.uint8)
        reproject(
            s1_valid.astype(np.uint8), aligned_valid, src_transform=s1_transform, src_crs=s1_crs,
            dst_transform=s2_transform, dst_crs=s2_crs, resampling=Resampling.nearest,
        )
        return aligned, aligned_valid > 0

    def predict(self, optical: bytes, sar: bytes, threshold: float = 0.5) -> dict[str, Any] | None:
        """Return dense water mask/probability/confidence for real S2 + S1 GeoTIFFs."""
        if not self.available:
            return None
        try:
            import torch
            from training.s1s2_water_dataset import S1_STORAGE_SCALE, S2_STORAGE_SCALE, normalize_s1, normalize_s2

            s2, s2_valid, s2_transform, s2_crs = self._read_raster(
                optical, 6, ("B02", "B03", "B04", "B08", "B11", "B12")
            )
            s1, s1_valid, s1_transform, s1_crs = self._read_raster(sar, 2, ("VV", "VH"))
            s1_aligned, s1_valid_aligned = self._align_s1_to_s2(
                s1, s1_valid, s1_transform, s1_crs, s2.shape[-2:], s2_transform, s2_crs
            )
            valid = s2_valid & s1_valid_aligned
            if not np.any(valid):
                raise ValueError("Optical and SAR inputs contain no jointly valid pixels after alignment.")
            if min(s2.shape[-2:]) < 8:
                raise ValueError("Inputs must be at least 8x8 pixels for the segmentation model.")

            s1_normalized = normalize_s1(s1_aligned / S1_STORAGE_SCALE, self.normalization_config)
            s2_normalized = normalize_s2(s2 / S2_STORAGE_SCALE, self.normalization_config)
            with torch.inference_mode():
                logits = self.model(
                    torch.from_numpy(s1_normalized).unsqueeze(0).to(self.device),
                    torch.from_numpy(s2_normalized).unsqueeze(0).to(self.device),
                )
                probability = torch.sigmoid(logits)[0, 0].cpu().numpy()
            water_mask = (probability > threshold) & valid
            confidence = float(np.mean(np.abs(probability[valid] - 0.5) * 2.0))
            return {
                "water_mask": water_mask,
                "water_probability": probability,
                "valid": valid,
                "confidence": confidence,
                "threshold": threshold,
            }
        except Exception as exc:  # noqa: BLE001 - preserve the existing heuristic fallback
            self.error = f"Water-segmentation inference failed: {exc}"
            return None

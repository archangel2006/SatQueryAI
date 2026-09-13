from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np


WATER_LABEL_TERMS = (
    "marine waters",
    "inland waters",
    "coastal waters",
    "water bodies",
    "water",
)
BUILT_UP_LABEL_TERMS = (
    "urban fabric",
    "industrial or commercial units",
    "industrial/commercial units",
    "road and rail networks",
    "road/rail networks",
    "port areas",
    "construction sites",
    "dump sites",
)


def _contains_term(label: str, terms: tuple[str, ...]) -> bool:
    normalized = " ".join(label.lower().replace("_", " ").split())
    return any(term in normalized for term in terms)


def semantic_groups(label_names: list[str], probabilities: np.ndarray) -> dict[str, float]:
    """Aggregate BigEarthNet class probabilities into water and built-up groups."""
    water = [probability for label, probability in zip(label_names, probabilities) if _contains_term(label, WATER_LABEL_TERMS)]
    built_up = [probability for label, probability in zip(label_names, probabilities) if _contains_term(label, BUILT_UP_LABEL_TERMS)]
    return {
        "water": float(max(water, default=0.0)),
        "built_up": float(max(built_up, default=0.0)),
    }


class LearnedFusion:
    """Optional checkpoint-backed scene classifier with deterministic fallback outside this class."""

    def __init__(self, checkpoint_path: str, device: str = "cpu") -> None:
        self.checkpoint_path = str(checkpoint_path)
        self.device_name = device
        self.model: Any = None
        self.label_names: list[str] = []
        self.device: Any = None
        self.error: str | None = None
        self._load()

    @property
    def available(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        if not self.checkpoint_path or not Path(self.checkpoint_path).is_file():
            self.error = "Fusion checkpoint path is not configured or does not exist."
            return
        try:
            import torch
            from torch import nn

            class Encoder(nn.Sequential):
                def __init__(self, channels: int) -> None:
                    super().__init__(
                        nn.Conv2d(channels, 32, 3, padding=1),
                        nn.BatchNorm2d(32),
                        nn.ReLU(inplace=True),
                        nn.MaxPool2d(2),
                        nn.Conv2d(32, 64, 3, padding=1),
                        nn.BatchNorm2d(64),
                        nn.ReLU(inplace=True),
                        nn.AdaptiveAvgPool2d(1),
                        nn.Flatten(),
                    )

            class Classifier(nn.Module):
                def __init__(self, optical_channels: int, sar_channels: int, classes: int) -> None:
                    super().__init__()
                    self.optical_encoder = Encoder(optical_channels)
                    self.sar_encoder = Encoder(sar_channels)
                    self.classifier = nn.Sequential(
                        nn.Linear(128, 128),
                        nn.ReLU(inplace=True),
                        nn.Dropout(0.2),
                        nn.Linear(128, classes),
                    )

                def forward(self, optical: Any, sar: Any) -> Any:
                    fused = torch.cat([self.optical_encoder(optical), self.sar_encoder(sar)], dim=1)
                    return self.classifier(fused)

            checkpoint = torch.load(self.checkpoint_path, map_location=self.device_name)
            state_dict = checkpoint.get("model_state_dict", checkpoint)
            optical_channels = int(checkpoint.get("optical_channels", 4))
            sar_channels = int(checkpoint.get("sar_channels", 2))
            classes = int(checkpoint.get("classes", len(checkpoint.get("label_names", []))))
            self.label_names = [str(label) for label in checkpoint.get("label_names", [])]
            if len(self.label_names) != classes:
                raise ValueError("Checkpoint label_names/classes metadata is inconsistent.")
            self.device = torch.device(self.device_name)
            self.model = Classifier(optical_channels, sar_channels, classes).to(self.device)
            self.model.load_state_dict(state_dict)
            self.model.eval()
        except Exception as exc:  # noqa: BLE001 - learned path must not break deterministic fallback
            self.model = None
            self.error = f"Could not load fusion checkpoint: {exc}"

    @staticmethod
    def _bands(data: bytes, names: tuple[str, ...]) -> np.ndarray:
        import rasterio
        from rasterio.io import MemoryFile

        with MemoryFile(data) as memory_file:
            with memory_file.open() as dataset:
                descriptions = tuple(description or "" for description in dataset.descriptions)
                indexes = []
                for name in names:
                    match = next((index for index, description in enumerate(descriptions, 1) if description.lower() == name.lower()), None)
                    indexes.append(match or (len(indexes) + 1))
                if max(indexes) > dataset.count:
                    raise ValueError(f"Raster does not contain required {names} bands.")
                return dataset.read(indexes).astype(np.float32)

    @staticmethod
    def _normalize(array: np.ndarray) -> np.ndarray:
        normalized = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        for channel in range(normalized.shape[0]):
            values = normalized[channel][np.isfinite(normalized[channel])]
            if values.size == 0:
                continue
            low, high = np.percentile(values, [2, 98])
            if high > low:
                normalized[channel] = np.clip((normalized[channel] - low) / (high - low), 0.0, 1.0)
        return normalized

    def predict(self, optical: bytes, sar: bytes) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            import torch
            import torch.nn.functional as functional

            optical_array = self._normalize(self._bands(optical, ("B02", "B03", "B04", "B08")))
            sar_array = self._normalize(self._bands(sar, ("VV", "VH")))
            if optical_array.shape[-2:] != sar_array.shape[-2:]:
                raise ValueError("Learned fusion inputs must have matching dimensions.")
            optical_tensor = functional.interpolate(torch.from_numpy(optical_array).unsqueeze(0), size=(120, 120), mode="bilinear", align_corners=False).to(self.device)
            sar_tensor = functional.interpolate(torch.from_numpy(sar_array).unsqueeze(0), size=(120, 120), mode="bilinear", align_corners=False).to(self.device)
            with torch.inference_mode():
                probabilities = torch.sigmoid(self.model(optical_tensor, sar_tensor))[0].cpu().numpy()
            groups = semantic_groups(self.label_names, probabilities)
            return {
                "groups": groups,
                "max_probability": float(np.max(probabilities, initial=0.0)),
                "label_count": len(self.label_names),
            }
        except Exception as exc:  # noqa: BLE001 - preserve deterministic fallback
            self.error = f"Learned fusion inference failed: {exc}"
            return None

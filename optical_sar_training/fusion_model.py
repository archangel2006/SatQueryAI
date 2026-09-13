from __future__ import annotations

import torch
from torch import Tensor, nn


class OpticalSarFusionClassifier(nn.Module):
    """Small two-encoder baseline for scene-level BigEarthNet labels."""

    def __init__(self, optical_channels: int = 4, sar_channels: int = 2, classes: int = 19) -> None:
        super().__init__()
        self.optical_encoder = self._encoder(optical_channels)
        self.sar_encoder = self._encoder(sar_channels)
        self.classifier = nn.Sequential(
            nn.Linear(128, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(128, classes),
        )

    @staticmethod
    def _encoder(channels: int) -> nn.Sequential:
        return nn.Sequential(
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

    def forward(self, optical: Tensor, sar: Tensor) -> Tensor:
        fused = torch.cat([self.optical_encoder(optical), self.sar_encoder(sar)], dim=1)
        return self.classifier(fused)
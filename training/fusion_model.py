from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


class ConvBlock(nn.Module):
    """Two consecutive Conv2d-BatchNorm2d-ReLU layers."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.block(x)


class FusionBlock(nn.Module):
    """Feature-level fusion of S1 and S2 representations."""

    def __init__(self, s1_channels: int, s2_channels: int, out_channels: int) -> None:
        super().__init__()
        self.fuse = nn.Sequential(
            nn.Conv2d(s1_channels + s2_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, s1_feat: Tensor, s2_feat: Tensor) -> Tensor:
        return self.fuse(torch.cat([s1_feat, s2_feat], dim=1))


class DecoderStage(nn.Module):
    """Upsampling + concatenation with skip connection + ConvBlock."""

    def __init__(self, in_channels: int, skip_channels: int, out_channels: int) -> None:
        super().__init__()
        self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.conv = ConvBlock(in_channels + skip_channels, out_channels)

    def forward(self, x: Tensor, skip: Tensor) -> Tensor:
        x_up = self.up(x)
        # Ensure spatial alignment in case of odd spatial dimensions
        if x_up.shape[-2:] != skip.shape[-2:]:
            x_up = F.interpolate(x_up, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return self.conv(torch.cat([x_up, skip], dim=1))


class OpticalSarFusionSegmenter(nn.Module):
    """Dual-Encoder Optical + SAR Water Segmentation Network.

    Architecture Target:
      S1 (2 ch: VV/VH)                 ──► S1 Encoder ──┐
                                                         ├──► Feature Fusion ──► Decoder ──► Water Logits [B, 1, H, W]
      S2 (6 ch: B/G/R/NIR/SWIR1/SWIR2) ──► S2 Encoder ──┘

    Key Features:
      - Dedicated multi-scale encoders for SAR and optical modalities.
      - Feature-level fusion at 4 spatial resolution scales.
      - U-Net style decoder preserving sharp water boundaries and small rivers/canals.
      - Single-channel output logits (binary water target).
    """

    def __init__(
        self,
        s1_channels: int = 2,
        s2_channels: int = 6,
        base_channels: int = 32,
    ) -> None:
        super().__init__()
        c = base_channels  # e.g. 32

        # 1. S1 SAR Encoder (2 channels: VV, VH)
        self.s1_enc0 = ConvBlock(s1_channels, c)
        self.s1_pool0 = nn.MaxPool2d(2)
        self.s1_enc1 = ConvBlock(c, c * 2)
        self.s1_pool1 = nn.MaxPool2d(2)
        self.s1_enc2 = ConvBlock(c * 2, c * 4)
        self.s1_pool2 = nn.MaxPool2d(2)
        self.s1_enc3 = ConvBlock(c * 4, c * 8)

        # 2. S2 Optical Encoder (6 channels: B, G, R, NIR, SWIR1, SWIR2)
        self.s2_enc0 = ConvBlock(s2_channels, c)
        self.s2_pool0 = nn.MaxPool2d(2)
        self.s2_enc1 = ConvBlock(c, c * 2)
        self.s2_pool1 = nn.MaxPool2d(2)
        self.s2_enc2 = ConvBlock(c * 2, c * 4)
        self.s2_pool2 = nn.MaxPool2d(2)
        self.s2_enc3 = ConvBlock(c * 4, c * 8)

        # 3. Multi-scale Feature Fusion
        self.fuse0 = FusionBlock(c, c, c)          # Level 0 (1x)
        self.fuse1 = FusionBlock(c * 2, c * 2, c * 2)  # Level 1 (2x down)
        self.fuse2 = FusionBlock(c * 4, c * 4, c * 4)  # Level 2 (4x down)
        self.fuse3 = FusionBlock(c * 8, c * 8, c * 8)  # Bottleneck (8x down)

        # 4. Decoder with skip connections from fused features
        self.dec2 = DecoderStage(in_channels=c * 8, skip_channels=c * 4, out_channels=c * 4)
        self.dec1 = DecoderStage(in_channels=c * 4, skip_channels=c * 2, out_channels=c * 2)
        self.dec0 = DecoderStage(in_channels=c * 2, skip_channels=c, out_channels=c)

        # 5. Single-channel Water Head (produces raw logits)
        self.head = nn.Conv2d(c, 1, kernel_size=1)

    @property
    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def forward(self, s1: Tensor, s2: Tensor) -> Tensor:
        """Forward pass for aligned S1 SAR and S2 Optical tensors.

        Args:
            s1: Sentinel-1 SAR tensor [B, 2, H, W]
            s2: Sentinel-2 Optical tensor [B, 6, H, W]

        Returns:
            Logits tensor [B, 1, H, W]
        """
        # Encoder Level 0 (H, W)
        s1_0 = self.s1_enc0(s1)
        s2_0 = self.s2_enc0(s2)
        f_0 = self.fuse0(s1_0, s2_0)

        # Encoder Level 1 (H/2, W/2)
        s1_1 = self.s1_enc1(self.s1_pool0(s1_0))
        s2_1 = self.s2_enc1(self.s2_pool0(s2_0))
        f_1 = self.fuse1(s1_1, s2_1)

        # Encoder Level 2 (H/4, W/4)
        s1_2 = self.s1_enc2(self.s1_pool1(s1_1))
        s2_2 = self.s2_enc2(self.s2_pool1(s2_1))
        f_2 = self.fuse2(s1_2, s2_2)

        # Bottleneck Level 3 (H/8, W/8)
        s1_3 = self.s1_enc3(self.s1_pool2(s1_2))
        s2_3 = self.s2_enc3(self.s2_pool2(s2_2))
        f_3 = self.fuse3(s1_3, s2_3)

        # Decoder
        d_2 = self.dec2(f_3, f_2)
        d_1 = self.dec1(d_2, f_1)
        d_0 = self.dec0(d_1, f_0)

        return self.head(d_0)

    def predict_probability(self, s1: Tensor, s2: Tensor) -> Tensor:
        """Return water probability map [B, 1, H, W] in range [0, 1]."""
        with torch.no_grad():
            logits = self.forward(s1, s2)
            return torch.sigmoid(logits)

    def predict_mask(self, s1: Tensor, s2: Tensor, threshold: float = 0.5) -> Tensor:
        """Return binary water mask [B, 1, H, W] (0 or 1)."""
        probs = self.predict_probability(s1, s2)
        return (probs > threshold).float()

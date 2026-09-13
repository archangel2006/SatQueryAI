"""model.py — Siamese encoder / U-Net decoder change detection model.

Architecture overview
---------------------
Both T1 and T2 images pass through a *shared* CNN encoder that produces
feature maps at four spatial scales.  At each scale the absolute difference
between the T1 and T2 feature maps is computed and concatenated with the
sum, giving the decoder rich change-sensitive representations.  A lightweight
U-Net decoder with skip connections upsamples back to the original resolution
and produces a single-channel logit map.

    T1 ──► Encoder ──► [E1, E2, E3, E4]
                                          ──► |diff| + sum at each scale
    T2 ──► Encoder ──► [E1, E2, E3, E4]
                                          ──► Decoder ──► [B, 1, H, W] logits

The model outputs *logits* (no sigmoid).  Apply sigmoid for probabilities or
use ``BCEWithLogitsLoss`` during training.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _conv_bn_relu(in_ch: int, out_ch: int, kernel: int = 3, padding: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, kernel, padding=padding, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class _EncoderBlock(nn.Module):
    """Two conv-BN-ReLU layers followed by max-pool.  Returns (pooled, skip)."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            _conv_bn_relu(in_ch, out_ch),
            _conv_bn_relu(out_ch, out_ch),
        )
        self.pool = nn.MaxPool2d(2, 2)

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor]:
        skip = self.conv(x)
        return self.pool(skip), skip


class _DecoderBlock(nn.Module):
    """Bilinear upsample + concatenate skip + two conv-BN-ReLU layers."""

    def __init__(self, in_ch: int, skip_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            _conv_bn_relu(in_ch + skip_ch, out_ch),
            _conv_bn_relu(out_ch, out_ch),
        )

    def forward(self, x: Tensor, skip: Tensor) -> Tensor:
        x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return self.conv(torch.cat([x, skip], dim=1))


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class SiameseChangeDetector(nn.Module):
    """Siamese encoder / U-Net decoder for pixel-level change detection.

    Args:
        in_channels:    Number of input channels per image (3 for RGB).
        base_channels:  Width of the first encoder stage.  Subsequent stages
                        double the channels up to ``8 × base_channels``.

    Input:
        image_a, image_b — both ``[B, in_channels, H, W]``

    Output:
        ``[B, 1, H, W]`` logit map (apply sigmoid for probabilities).
    """

    def __init__(self, in_channels: int = 3, base_channels: int = 32) -> None:
        super().__init__()
        c = base_channels   # 32

        # Shared encoder — weights are identical for T1 and T2
        self.enc1 = _EncoderBlock(in_channels, c)       # skip: [B, c,   H/2,  W/2]  (before pool)
        self.enc2 = _EncoderBlock(c,           c * 2)   # skip: [B, 2c,  H/4,  W/4]
        self.enc3 = _EncoderBlock(c * 2,       c * 4)   # skip: [B, 4c,  H/8,  W/8]
        self.enc4 = _EncoderBlock(c * 4,       c * 8)   # skip: [B, 8c,  H/16, W/16]

        # Bottleneck (operates on pooled enc4 output)
        self.bottleneck = nn.Sequential(
            _conv_bn_relu(c * 8, c * 16),
            _conv_bn_relu(c * 16, c * 16),
        )

        # At each scale we fuse T1 and T2 features:
        #   fused = cat(|f_a - f_b|, f_a + f_b)  →  2 × channels
        # The decoder skip channels are therefore 2× the encoder skip channels.
        self.dec4 = _DecoderBlock(c * 16, c * 8  * 2, c * 8)
        self.dec3 = _DecoderBlock(c * 8,  c * 4  * 2, c * 4)
        self.dec2 = _DecoderBlock(c * 4,  c * 2  * 2, c * 2)
        self.dec1 = _DecoderBlock(c * 2,  c      * 2, c)

        self.head = nn.Conv2d(c, 1, kernel_size=1)

    # ------------------------------------------------------------------
    def _encode(self, x: Tensor) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
        """Run the shared encoder and return (bottleneck_input, s1, s2, s3, s4)."""
        x, s1 = self.enc1(x)
        x, s2 = self.enc2(x)
        x, s3 = self.enc3(x)
        x, s4 = self.enc4(x)
        return x, s1, s2, s3, s4

    @staticmethod
    def _fuse(fa: Tensor, fb: Tensor) -> Tensor:
        """Fuse two feature maps: cat(|fa - fb|, fa + fb)."""
        return torch.cat([torch.abs(fa - fb), fa + fb], dim=1)

    # ------------------------------------------------------------------
    def forward(self, image_a: Tensor, image_b: Tensor) -> Tensor:
        # Encode both images with shared weights
        bot_a, s1_a, s2_a, s3_a, s4_a = self._encode(image_a)
        bot_b, s1_b, s2_b, s3_b, s4_b = self._encode(image_b)

        # Bottleneck on fused deepest features
        bot = self.bottleneck(torch.abs(bot_a - bot_b) + (bot_a + bot_b) * 0.5)

        # Decoder with fused skip connections
        x = self.dec4(bot,  self._fuse(s4_a, s4_b))
        x = self.dec3(x,    self._fuse(s3_a, s3_b))
        x = self.dec2(x,    self._fuse(s2_a, s2_b))
        x = self.dec1(x,    self._fuse(s1_a, s1_b))

        return self.head(x)   # [B, 1, H, W] logits


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------

class CombinedLoss(nn.Module):
    """BCE-with-logits + soft Dice loss.

    Args:
        dice_weight:  Weight applied to the Dice term.
        pos_weight:   Optional scalar tensor passed to BCEWithLogitsLoss to
                      up-weight the positive (changed) class.
    """

    def __init__(self, dice_weight: float = 1.0, pos_weight: Tensor | None = None) -> None:
        super().__init__()
        self.dice_weight = dice_weight
        self.bce = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    def _dice(self, logits: Tensor, targets: Tensor, eps: float = 1e-6) -> Tensor:
        probs = torch.sigmoid(logits)
        # Flatten spatial dims
        probs   = probs.view(probs.size(0), -1)
        targets = targets.view(targets.size(0), -1)
        intersection = (probs * targets).sum(dim=1)
        union = probs.sum(dim=1) + targets.sum(dim=1)
        dice = (2.0 * intersection + eps) / (union + eps)
        return 1.0 - dice.mean()

    def forward(self, logits: Tensor, targets: Tensor) -> Tensor:
        return self.bce(logits, targets) + self.dice_weight * self._dice(logits, targets)

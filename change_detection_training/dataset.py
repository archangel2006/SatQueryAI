"""dataset.py — LEVIR-CD bi-temporal change detection dataset.

Directory layout expected:
    <root>/
        train/  A/  B/  label/
        val/    A/  B/  label/
        test/   A/  B/  label/

Each A image, B image, and label share the same filename.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchvision.transforms.functional as TF
from PIL import Image
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

# ImageNet-style mean/std used for RGB normalisation.
_MEAN = (0.485, 0.456, 0.406)
_STD  = (0.229, 0.224, 0.225)


class ChangeDetectionDataset(Dataset[dict[str, Any]]):
    """PyTorch Dataset for LEVIR-CD (or any A / B / label layout).

    Args:
        root:       Path to the split directory, e.g. ``/content/LEVIR-CD/train``.
        split:      One of ``"train"``, ``"val"``, ``"test"``.  Used only to
                    decide whether augmentation is applied.
        image_size: Spatial size ``(H, W)`` to resize every sample to.
        augment:    Override augmentation flag.  Defaults to ``True`` for
                    ``"train"`` and ``False`` otherwise.
    """

    def __init__(
        self,
        root: str | Path,
        split: str,
        image_size: int | tuple[int, int] = 256,
        augment: bool | None = None,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.image_size: tuple[int, int] = (
            (image_size, image_size) if isinstance(image_size, int) else tuple(image_size)  # type: ignore[assignment]
        )
        self.augment = augment if augment is not None else (split == "train")

        self.dir_a     = self.root / "A"
        self.dir_b     = self.root / "B"
        self.dir_label = self.root / "label"

        for directory in (self.dir_a, self.dir_b, self.dir_label):
            if not directory.is_dir():
                raise FileNotFoundError(f"Expected directory not found: {directory}")

        # Build file list matched by stem across all three folders.
        a_stems = {p.stem: p for p in sorted(self.dir_a.iterdir()) if p.is_file()}
        b_stems = {p.stem: p for p in sorted(self.dir_b.iterdir()) if p.is_file()}
        l_stems = {p.stem: p for p in sorted(self.dir_label.iterdir()) if p.is_file()}

        common = sorted(set(a_stems) & set(b_stems) & set(l_stems))
        if not common:
            raise RuntimeError(f"No matching filenames found across A / B / label in {self.root}")

        only_a = set(a_stems) - set(b_stems) - set(l_stems)
        only_b = set(b_stems) - set(a_stems) - set(l_stems)
        only_l = set(l_stems) - set(a_stems) - set(b_stems)
        if only_a or only_b or only_l:
            import warnings
            warnings.warn(
                f"Skipping unmatched files — A-only: {len(only_a)}, "
                f"B-only: {len(only_b)}, label-only: {len(only_l)}",
                stacklevel=2,
            )

        self.samples: list[tuple[Path, Path, Path]] = [
            (a_stems[s], b_stems[s], l_stems[s]) for s in common
        ]

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.samples)

    # ------------------------------------------------------------------
    def _load_rgb(self, path: Path) -> Image.Image:
        img = Image.open(path).convert("RGB")
        return img

    def _load_mask(self, path: Path) -> Image.Image:
        mask = Image.open(path).convert("L")
        return mask

    # ------------------------------------------------------------------
    def _apply_transforms(
        self,
        img_a: Image.Image,
        img_b: Image.Image,
        mask: Image.Image,
    ) -> tuple[Image.Image, Image.Image, Image.Image]:
        """Resize and optionally augment.  A, B, and mask receive identical ops."""
        # Resize
        img_a = TF.resize(img_a, list(self.image_size), interpolation=TF.InterpolationMode.BILINEAR)
        img_b = TF.resize(img_b, list(self.image_size), interpolation=TF.InterpolationMode.BILINEAR)
        mask  = TF.resize(mask,  list(self.image_size), interpolation=TF.InterpolationMode.NEAREST)

        if not self.augment:
            return img_a, img_b, mask

        # Horizontal flip
        if random.random() > 0.5:
            img_a = TF.hflip(img_a)
            img_b = TF.hflip(img_b)
            mask  = TF.hflip(mask)

        # Vertical flip
        if random.random() > 0.5:
            img_a = TF.vflip(img_a)
            img_b = TF.vflip(img_b)
            mask  = TF.vflip(mask)

        # 90-degree rotation (0 / 90 / 180 / 270)
        angle = random.choice([0, 90, 180, 270])
        if angle:
            img_a = TF.rotate(img_a, angle)
            img_b = TF.rotate(img_b, angle)
            mask  = TF.rotate(mask,  angle)

        return img_a, img_b, mask

    # ------------------------------------------------------------------
    def _to_tensor(self, img: Image.Image) -> Tensor:
        """Convert PIL RGB image → normalised float tensor [3, H, W]."""
        t = TF.to_tensor(img)           # [3, H, W], float32 in [0, 1]
        t = TF.normalize(t, _MEAN, _STD)
        return t

    def _mask_to_tensor(self, mask: Image.Image) -> Tensor:
        """Convert PIL grayscale mask → binary float tensor [1, H, W]."""
        arr = np.array(mask, dtype=np.float32)
        arr = (arr > 127).astype(np.float32)   # binarise
        return torch.from_numpy(arr).unsqueeze(0)   # [1, H, W]

    # ------------------------------------------------------------------
    def __getitem__(self, index: int) -> dict[str, Any]:
        path_a, path_b, path_label = self.samples[index]

        img_a = self._load_rgb(path_a)
        img_b = self._load_rgb(path_b)
        mask  = self._load_mask(path_label)

        img_a, img_b, mask = self._apply_transforms(img_a, img_b, mask)

        return {
            "image_a":  self._to_tensor(img_a),
            "image_b":  self._to_tensor(img_b),
            "mask":     self._mask_to_tensor(mask),
            "filename": path_a.name,
        }


# ---------------------------------------------------------------------------
# DataLoader factory
# ---------------------------------------------------------------------------

def build_loader(
    dataset_root: str | Path,
    split: str,
    image_size: int | tuple[int, int] = 256,
    batch_size: int = 8,
    num_workers: int = 2,
    augment: bool | None = None,
    pin_memory: bool = True,
) -> DataLoader:
    """Return a DataLoader for the requested split.

    Args:
        dataset_root: Root of the LEVIR-CD dataset (contains train/ val/ test/).
        split:        ``"train"``, ``"val"``, or ``"test"``.
        image_size:   Spatial size fed to the model.
        batch_size:   Samples per batch.
        num_workers:  Parallel data-loading workers.
        augment:      Override augmentation flag.
        pin_memory:   Pin host memory for faster GPU transfer.
    """
    split_root = Path(dataset_root) / split
    dataset = ChangeDetectionDataset(
        root=split_root,
        split=split,
        image_size=image_size,
        augment=augment,
    )
    shuffle = split == "train"
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=pin_memory and torch.cuda.is_available(),
        drop_last=shuffle,   # drop incomplete last batch only during training
    )

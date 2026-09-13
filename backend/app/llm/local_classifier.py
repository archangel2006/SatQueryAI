"""Local scene/land-cover classifier — the fine-tuned model this project's
plan calls for, actually invoked at inference time.

Loads the ConvNeXt-tiny checkpoint produced by `train/train_convnext.py`
(trained on Kaggle — see `train/README.md`; never trained locally) from
`models/bentxt_convnext.pt` at the repo root. If that file, or `torch`/
`timm`/`torchvision`, aren't available, the classifier disables itself and
`classify()` returns None — the rest of the app keeps working normally via
Gemini alone. This is a soft dependency, not a hard requirement.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# backend/app/llm/local_classifier.py -> repo root is 3 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHECKPOINT_PATH = _REPO_ROOT / "models" / "bentxt_convnext.pt"

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    topk: list[tuple[str, float]]


class SceneClassifier:
    """Wraps a locally fine-tuned ConvNeXt-tiny scene/land-cover classifier."""

    def __init__(self, checkpoint_path: str | Path) -> None:
        self._checkpoint_path = Path(checkpoint_path)
        self._model = None
        self._labels: list[str] = []
        self._img_size = 224
        self._load()

    @property
    def available(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        if not self._checkpoint_path.exists():
            logger.warning(
                "Scene classifier checkpoint not found at %s; classifier disabled. "
                "Run train/kaggle_notebook.ipynb on Kaggle (see train/README.md) and "
                "place the resulting checkpoint there to enable it.",
                self._checkpoint_path,
            )
            return

        try:
            import timm  # noqa: F401
            import torch
        except ImportError as exc:
            logger.warning(
                "torch/timm not installed; scene classifier disabled (%s). "
                "Add them to backend/requirements.txt to enable local classification.",
                exc,
            )
            return

        try:
            checkpoint = torch.load(self._checkpoint_path, map_location="cpu")
            labels = checkpoint["labels"]
            model_name = checkpoint.get("model_name", "convnext_tiny")
            model = timm.create_model(model_name, pretrained=False, num_classes=len(labels))
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()

            self._model = model
            self._labels = labels
            self._img_size = checkpoint.get("img_size", 224)
            logger.info(
                "Loaded scene classifier from %s (%d classes: %s).",
                self._checkpoint_path,
                len(labels),
                labels,
            )
        except Exception:
            logger.exception(
                "Failed to load scene classifier checkpoint at %s; classifier disabled.",
                self._checkpoint_path,
            )
            self._model = None

    def classify(self, image_png_bytes: bytes, top_k: int = 3) -> ClassificationResult | None:
        if self._model is None:
            return None
        try:
            import torch
            from PIL import Image
            from torchvision import transforms

            img = Image.open(io.BytesIO(image_png_bytes)).convert("RGB")
            tfm = transforms.Compose(
                [
                    transforms.Resize((self._img_size, self._img_size)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
                ]
            )
            tensor = tfm(img).unsqueeze(0)

            with torch.no_grad():
                logits = self._model(tensor)
                probs = torch.softmax(logits, dim=1)[0]

            k = min(top_k, len(self._labels))
            top_probs, top_idxs = torch.topk(probs, k)
            topk = [
                (self._labels[idx], float(p))
                for p, idx in zip(top_probs.tolist(), top_idxs.tolist())
            ]
            label, confidence = topk[0]
            return ClassificationResult(label=label, confidence=confidence, topk=topk)
        except Exception:
            logger.exception("Scene classifier inference failed; skipping for this request.")
            return None


_classifier: SceneClassifier | None = None


def get_classifier(settings: Settings | None = None) -> SceneClassifier:
    global _classifier
    if _classifier is not None:
        return _classifier
    cfg = settings or get_settings()
    path = cfg.local_classifier_path or str(DEFAULT_CHECKPOINT_PATH)
    _classifier = SceneClassifier(path)
    return _classifier


def set_classifier(classifier: SceneClassifier | None) -> None:
    global _classifier
    _classifier = classifier

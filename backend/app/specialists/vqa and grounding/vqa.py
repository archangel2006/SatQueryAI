"""VQA (Visual Question Answering) tool — Dev 2 implementation.

Accepts an image (preprocessed PIL.Image, NumPy array, or raw GeoTIFF/PNG bytes/path)
and a natural-language question, passes through Dev 1 preprocessing, executes
VQA via GeoChat, and returns a ToolOutput.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image
import torch

from app.schemas import ToolOutput
from app.tools.loader import get_fresh_conv, get_geochat_model
from app.tools.preprocess import preprocess_image

logger = logging.getLogger(__name__)

_CONV_TEMPLATE = "llava_v1"


def _to_pil(image: Image.Image | np.ndarray | bytes | str | Path) -> Image.Image | None:
    """Normalise input image to a clean RGB PIL Image using Dev 1 preprocessing.

    Accepts:
    - PIL.Image.Image
    - HxWx3 uint8 RGB NumPy array
    - Multi-band NumPy array (dispatched to preprocess_image)
    - Raw file bytes (GeoTIFF, PNG, JPEG)
    - Local file path (str or Path)

    Returns None on unsupported or invalid input.
    """
    if isinstance(image, Image.Image):
        return image.convert("RGB")

    if isinstance(image, (bytes, str, Path)):
        try:
            return preprocess_image(image)
        except Exception as exc:
            logger.error("Failed to preprocess image input: %s", exc)
            return None

    if isinstance(image, np.ndarray):
        if image.ndim == 3 and image.shape[2] == 3:
            return Image.fromarray(image.astype("uint8"), "RGB")
        try:
            return preprocess_image(image)
        except Exception as exc:
            logger.error("NumPy array preprocessing failed for shape %s: %s", image.shape, exc)
            return None

    logger.error("Unsupported image type for VQA: %s", type(image))
    return None


def vqa(
    image: Image.Image | np.ndarray | bytes | str | Path,
    query: str,
) -> ToolOutput:
    """Run Visual Question Answering via GeoChat.

    Args:
        image: Pre-processed image as PIL.Image or HxWx3 NumPy RGB array, or
               raw satellite GeoTIFF/PNG bytes/path (automatically preprocessed via Dev 1).
        query: Natural-language question. Must be non-empty.

    Returns:
        ToolOutput(text=<answer>, overlay=None, score=None) on success.
        ToolOutput(text=None, overlay=None, score=None) on any failure.
        score is always None per Master Build Plan (GeoChat does not emit confidence scores).
    """
    if not query or not query.strip():
        logger.warning("vqa() called with empty query")
        return ToolOutput(text=None, overlay=None, score=None)

    pil_img = _to_pil(image)
    if pil_img is None:
        return ToolOutput(text=None, overlay=None, score=None)

    chat = get_geochat_model()
    if chat is None:
        logger.error("GeoChat model unavailable")
        return ToolOutput(text=None, overlay=None, score=None)

    try:
        chat_state = get_fresh_conv(_CONV_TEMPLATE)
        img_list: list = []

        # Step 1 — register image in conv and img_list (adds DEFAULT_IMAGE_TOKEN)
        chat.upload_img(pil_img, chat_state, img_list)

        # Step 2 — add user question to conv
        chat.ask(query, chat_state)

        # Step 3 — encode image tensor (as in geochat_demo.py)
        if img_list and not isinstance(img_list[0], torch.Tensor):
            chat.encode_img(img_list)

        # Step 4 — stream-generate answer
        streamer = chat.stream_answer(
            conv=chat_state,
            img_list=img_list,
            temperature=0.2,  # low temp for factual VQA
            max_new_tokens=500,
            max_length=2000,
        )

        output = "".join(streamer)

        return ToolOutput(text=output.strip(), overlay=None, score=None)

    except Exception as exc:
        logger.error("VQA inference failed: %s", exc)
        return ToolOutput(text=None, overlay=None, score=None)

"""Grounding tool — Dev 2 implementation.

Accepts an image (preprocessed PIL.Image, NumPy array, or raw GeoTIFF/PNG bytes/path)
and a natural-language grounding query, passes through Dev 1 preprocessing, calls
GeoChat, parses spatial tokens ({<x1><y1><x2><y2>} on a 0-100 grid), renders
a visual overlay PNG, and returns a ToolOutput.

GeoChat grounding token format (from geochat_demo.py):
  Multi-entity: <p>label</p>{<x1><y1><x2><y2>}  (optionally with angle as 5th int)
  Single-entity: {<x1><y1><x2><y2>}
  Coordinates are in 0–100 space and are scaled to pixel space before drawing.
"""
from __future__ import annotations

import io
import logging
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import torch

from app.schemas import ToolOutput
from app.tools.loader import get_fresh_conv, get_geochat_model
from app.tools.preprocess import preprocess_image

logger = logging.getLogger(__name__)

_CONV_TEMPLATE = "llava_v1"

# GeoChat normalises bounding boxes to this integer grid (0–100)
_BBOX_SCALE = 100

_COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (210, 210, 0),
    (255, 0, 255), (0, 255, 255), (114, 128, 250), (0, 165, 255),
    (0, 128, 0), (144, 238, 144), (238, 238, 175), (255, 191, 0),
    (0, 128, 0), (226, 43, 138), (255, 0, 255), (0, 215, 255),
]


def _extract_substrings(text: str) -> list[str]:
    """Extract '<label></p>{coords}' substrings from a multi-entity grounding response."""
    idx = text.rfind("}")
    if idx != -1:
        text = text[: idx + 1]
    # First match explicit <p>label</p>{coords} patterns
    matches = re.findall(r"<p>(.*?)</p>((?:\{<[^>]+>\})+)", text)
    if matches:
        return [f"{label}</p>{coords}" for label, coords in matches]
    return re.findall(r"<p>(.*?)\}(?!<)", text)


def _rotate_bbox(top_right: tuple, bottom_left: tuple, angle_deg: float) -> np.ndarray:
    center = (
        (top_right[0] + bottom_left[0]) / 2,
        (top_right[1] + bottom_left[1]) / 2,
    )
    rot = cv2.getRotationMatrix2D(center, angle_deg, 1)
    corners = np.array(
        [
            [bottom_left[0], bottom_left[1]],
            [top_right[0], bottom_left[1]],
            [top_right[0], top_right[1]],
            [bottom_left[0], top_right[1]],
        ],
        dtype=np.float32,
    )
    return cv2.transform(np.array([corners]), rot)[0]


def _is_overlapping(r1: tuple, r2: tuple) -> bool:
    x1, y1, x2, y2 = r1
    x3, y3, x4, y4 = r2
    return not (x2 < x3 or x1 > x4 or y2 < y3 or y1 > y4)


def _iou(b1: tuple, b2: tuple) -> float:
    x1, y1, x2, y2 = b1
    x3, y3, x4, y4 = b2
    ix1, iy1, ix2, iy2 = max(x1, x3), max(y1, y3), min(x2, x4), min(y2, y4)
    inter = max(0, ix2 - ix1 + 1) * max(0, iy2 - iy1 + 1)
    a1 = (x2 - x1 + 1) * (y2 - y1 + 1)
    a2 = (x4 - x3 + 1) * (y4 - y3 + 1)
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _reverse_escape(text: str) -> str:
    for ch in ["\\<", "\\>"]:
        text = text.replace(ch, ch[1:])
    return text


def _parse_entities(generation: str, image_w: int, image_h: int):
    """Parse GeoChat grounding tokens into pixel-space bounding-box lists.

    Returns (mode, entities) where:
      mode = 'all' | 'single' | None
      entities = dict[label -> list[[x1,y1,x2,y2,angle]]] for 'all'
               = list[[x1,y1,x2,y2,angle]]                for 'single'
               = None if no valid boxes found
    """
    string_list = _extract_substrings(generation)

    if string_list:
        mode = "all"
        entities: dict[str, list] = defaultdict(list)
        for raw in string_list:
            try:
                obj, coord_str = raw.split("</p>")
            except ValueError:
                continue
            coord_str = coord_str.replace("}{", "}<delim>{")
            for bbox_str in coord_str.split("<delim>"):
                ints = re.findall(r"-?\d+", bbox_str)
                if len(ints) < 4:
                    continue
                angle = int(ints[4]) if len(ints) >= 5 else 0
                x0, y0, x1, y1 = (int(v) for v in ints[:4])
                entities[obj].append([
                    x0 / _BBOX_SCALE * image_w,
                    y0 / _BBOX_SCALE * image_h,
                    x1 / _BBOX_SCALE * image_w,
                    y1 / _BBOX_SCALE * image_h,
                    angle,
                ])
        return (mode, entities) if entities else (None, None)

    # single/unlabeled entity fallback
    ints = re.findall(r"-?\d+", generation)
    if len(ints) >= 4:
        # Group coordinates into chunks of 4 (or 5 if angle present)
        single_boxes = []
        idx = 0
        while idx + 4 <= len(ints):
            x0, y0, x1, y1 = (int(v) for v in ints[idx : idx + 4])
            angle = 0
            idx += 4
            single_boxes.append([
                x0 / _BBOX_SCALE * image_w,
                y0 / _BBOX_SCALE * image_h,
                x1 / _BBOX_SCALE * image_w,
                y1 / _BBOX_SCALE * image_h,
                angle,
            ])
        if single_boxes:
            return ("single", single_boxes)

    return (None, None)


def _render_overlay(pil_img: Image.Image, generation: str) -> Image.Image | None:
    """Draw GeoChat bounding-box tokens onto the image.

    Adapted from geochat_demo.visualize_all_bbox_together with boundary clamping.
    Returns None when no valid boxes are found in the generation text.
    """
    image_w, image_h = pil_img.size
    img_np = np.array(pil_img)
    if img_np.ndim == 2:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_GRAY2RGB)
    elif img_np.shape[2] == 4:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)

    mode, entities = _parse_entities(generation, image_w, image_h)
    if mode is None or entities is None:
        return None

    canvas = img_np.copy()

    text_size = 0.4
    text_line = 1
    box_line = 2
    (c_width, text_h), _ = cv2.getTextSize("F", cv2.FONT_HERSHEY_COMPLEX, text_size, text_line)
    base_h = int(text_h * 0.675)
    text_offset = text_h - base_h
    text_spaces = 2
    prev_bboxes: list[dict] = []

    # Build a uniform list of (label, bboxes) regardless of mode
    if mode == "all":
        entity_pairs = list(entities.items())          # [(label, [bbox, ...]), ...]
    else:
        entity_pairs = [("object", entities)]          # entities is [[x1,y1,x2,y2,angle], ...]

    for color_idx, (label, bboxes) in enumerate(entity_pairs):
        color = _COLORS[color_idx % len(_COLORS)]

        for (x1n, y1n, x2n, y2n, angle) in bboxes:
            ox1, oy1, ox2, oy2, ang = int(x1n), int(y1n), int(x2n), int(y2n), int(angle)
            rotated = _rotate_bbox((ox1, oy1), (ox2, oy2), ang)
            canvas = cv2.polylines(
                canvas, [rotated.astype(np.int32)], isClosed=True, thickness=box_line, color=color
            )

            if mode == "all":
                lo, ro = box_line // 2 + box_line % 2, box_line // 2 + box_line % 2 + 1
                lx, ly = ox1 - lo, oy1 - lo
                if ly < text_h + text_offset + 2 * text_spaces:
                    ly = oy1 + ro + text_h + text_offset + 2 * text_spaces
                    lx = ox1 + ro

                (tw, th), _ = cv2.getTextSize(f"  {label}", cv2.FONT_HERSHEY_COMPLEX, text_size, text_line)
                bg = (lx, ly - (th + text_offset + 2 * text_spaces), lx + tw, ly)

                skip = False
                for pb in prev_bboxes:
                    if _iou(bg, pb["bbox"]) > 0.95 and pb["phrase"] == label:
                        skip = True
                        break
                    while _is_overlapping(bg, pb["bbox"]):
                        shift = th + text_offset + 2 * text_spaces
                        bg = (bg[0], bg[1] + shift, bg[2], bg[3] + shift)
                        ly += shift
                        if bg[3] >= image_h:
                            bg = (bg[0], max(0, image_h - shift), bg[2], image_h)
                            ly = image_h
                            break

                if not skip:
                    alpha = 0.5
                    # Boundary clamp to prevent wrap-around indices
                    i_start = max(0, min(image_h, bg[1]))
                    i_end = max(0, min(image_h, bg[3]))
                    j_start = max(0, min(image_w, bg[0]))
                    j_end = max(0, min(image_w, bg[2]))

                    for i in range(i_start, i_end):
                        for j in range(j_start, j_end):
                            bg_color = color if j < bg[0] + 1.35 * c_width else (255, 255, 255)
                            canvas[i, j] = (
                                alpha * canvas[i, j] + (1 - alpha) * np.array(bg_color)
                            ).astype(np.uint8)
                    cv2.putText(
                        canvas, f"  {label}",
                        (max(0, lx), max(text_h, ly - text_offset - text_spaces)),
                        cv2.FONT_HERSHEY_COMPLEX, text_size, (0, 0, 0), text_line, cv2.LINE_AA,
                    )
                    prev_bboxes.append({"bbox": bg, "phrase": label})

    return Image.fromarray(canvas)


def _overlay_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _to_pil(image: Image.Image | np.ndarray | bytes | str | Path) -> Image.Image | None:
    """Normalise image to PIL RGB, passing raw bytes or arrays through Dev 1 preprocessing."""
    if isinstance(image, Image.Image):
        return image.convert("RGB")

    if isinstance(image, (bytes, str, Path)):
        try:
            return preprocess_image(image)
        except Exception as exc:
            logger.error("Failed to preprocess image for Grounding: %s", exc)
            return None

    if isinstance(image, np.ndarray):
        if image.ndim == 3 and image.shape[2] == 3:
            return Image.fromarray(image.astype("uint8"), "RGB")
        try:
            return preprocess_image(image)
        except Exception as exc:
            logger.error("NumPy array preprocessing failed for shape %s: %s", image.shape, exc)
            return None

    logger.error("Unsupported image type for Grounding: %s", type(image))
    return None


def ground(
    image: Image.Image | np.ndarray | bytes | str | Path,
    query: str,
) -> ToolOutput:
    """Run visual grounding via GeoChat.

    Args:
        image: Pre-processed image as PIL.Image or HxWx3 NumPy RGB array, or
               raw GeoTIFF/PNG bytes/path (automatically preprocessed via Dev 1).
        query: Grounding query, e.g. "Locate the buildings" or
               "[identify] what is this {<x><y><x><y>}".

    Returns:
        ToolOutput(text=<model output>, overlay=<PNG bytes or None>, score=None)
        overlay is None when GeoChat finds no spatial region.
        score is always None (GeoChat does not output grounding confidence).
    """
    if not query or not query.strip():
        logger.warning("ground() called with empty query")
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

        # Step 1: Upload image
        chat.upload_img(pil_img, chat_state, img_list)

        # Step 2: Ask query
        chat.ask(query, chat_state)

        # Step 3: Encode image
        if img_list and not isinstance(img_list[0], torch.Tensor):
            chat.encode_img(img_list)

        # Step 4: Stream answer
        streamer = chat.stream_answer(
            conv=chat_state,
            img_list=img_list,
            temperature=0.2,
            max_new_tokens=500,
            max_length=2000,
        )
        raw_output = "".join(streamer)

        # Unescape Markdown escapes added by GeoChat demo's escape_markdown()
        unescaped = _reverse_escape(raw_output.strip())

        # Render overlay from GeoChat's grounding tokens
        overlay_img = _render_overlay(pil_img, unescaped)
        overlay_bytes = _overlay_to_bytes(overlay_img) if overlay_img is not None else None

        return ToolOutput(text=unescaped, overlay=overlay_bytes, score=None)

    except Exception as exc:
        logger.error("Grounding inference failed: %s", exc)
        return ToolOutput(text=None, overlay=None, score=None)

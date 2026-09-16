from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.io.geotiff import preview_from_bytes
from app.llm.gemini import FakeLLM, get_llm
from app.schemas import AskGroundedResponse, AskSatqueryResponse

ASK_VLM_TIMEOUT_SEC = 30.0
ASK_VLM_AUTO_TIMEOUT_SEC = 15.0
NGROK_SKIP_HEADER = {"ngrok-skip-browser-warning": "1"}
NARRATOR_MODEL = "gemini-narrator"

router = APIRouter(tags=["ask-vlm"])


class SatqueryVlmError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def rgb_png_from_upload(data: bytes, filename: str) -> bytes:
    """Decode GeoTIFF/PNG/JPEG the same way /preview does, as RGB PNG bytes."""
    preview_b64, _meta = preview_from_bytes(data, filename)
    return base64.b64decode(preview_b64)


def _vlm_url() -> str:
    return get_settings().satquery_vlm_url.strip()


async def post_vlm(
    url: str,
    png_bytes: bytes,
    question: str,
    timeout: float,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(
            url,
            files={"image": ("scene.png", png_bytes, "image/png")},
            data={"question": question},
            headers=NGROK_SKIP_HEADER,
        )


async def query_vlm(
    png_bytes: bytes,
    question: str,
    timeout: float = ASK_VLM_TIMEOUT_SEC,
) -> tuple[str, float]:
    url = _vlm_url()
    if not url:
        raise SatqueryVlmError(
            503,
            "SATQUERY_VLM_URL is not configured.",
        )
    started = time.perf_counter()
    try:
        response = await post_vlm(url, png_bytes, question, timeout)
    except httpx.TimeoutException as exc:
        raise SatqueryVlmError(504, "SatQuery VLM timed out.") from exc
    except httpx.HTTPError as exc:
        raise SatqueryVlmError(502, f"SatQuery VLM unreachable: {exc}") from exc

    latency = time.perf_counter() - started
    if response.status_code >= 400:
        raise SatqueryVlmError(
            502,
            f"SatQuery VLM failed with HTTP {response.status_code}.",
        )
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise SatqueryVlmError(502, "SatQuery VLM returned non-JSON.") from exc
    answer = payload.get("answer") if isinstance(payload, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise SatqueryVlmError(502, "SatQuery VLM returned no answer.")
    return answer.strip(), latency


def _narrator_prompt(question: str, fact: str) -> str:
    return (
        f"The user asked: {question}\n"
        f"A remote-sensing VLM extracted this fact: {fact}\n"
        "Rewrite this as a natural one-or-two-sentence answer using the image. "
        "Do not contradict the fact. Do not invent numbers the VLM did not provide."
    )


def _narrate_fact(question: str, fact: str, png_bytes: bytes) -> str:
    llm = get_llm()
    if isinstance(llm, FakeLLM):
        return fact
    try:
        text = llm.answer([], _narrator_prompt(question, fact), png_bytes).strip()
    except Exception:
        return fact
    return text or fact


def _gemini_only_answer(question: str, png_bytes: bytes) -> str:
    llm = get_llm()
    return llm.answer([], question, png_bytes).strip() or question


async def _png_from_form(image: UploadFile, question: str) -> tuple[bytes, str]:
    text = (question or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Question is required.")
    data = await image.read()
    filename = image.filename or "upload.bin"
    try:
        return rgb_png_from_upload(data, filename), text
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Could not read image: {exc}",
        ) from exc


@router.post("/ask_satquery", response_model=AskSatqueryResponse)
async def ask_satquery(
    image: UploadFile = File(...),
    question: str = Form(...),
) -> AskSatqueryResponse:
    png_bytes, text = await _png_from_form(image, question)
    try:
        answer, latency = await query_vlm(png_bytes, text, ASK_VLM_TIMEOUT_SEC)
    except SatqueryVlmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AskSatqueryResponse(
        answer=answer,
        model="satquery-vlm",
        latency_sec=round(latency, 3),
    )


@router.post("/ask_grounded", response_model=AskGroundedResponse)
async def ask_grounded(
    image: UploadFile = File(...),
    question: str = Form(...),
) -> AskGroundedResponse:
    png_bytes, text = await _png_from_form(image, question)
    try:
        fact, latency = await query_vlm(png_bytes, text, ASK_VLM_TIMEOUT_SEC)
    except SatqueryVlmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    narrated = _narrate_fact(text, fact, png_bytes)
    return AskGroundedResponse(
        vlm_fact=fact,
        narrated_answer=narrated,
        model_chain=["satquery-vlm", NARRATOR_MODEL],
        latency_sec=round(latency, 3),
        path_used="satquery-grounded",
    )


@router.post("/ask_auto", response_model=AskGroundedResponse)
async def ask_auto(
    image: UploadFile = File(...),
    question: str = Form(...),
) -> AskGroundedResponse:
    png_bytes, text = await _png_from_form(image, question)
    try:
        fact, latency = await query_vlm(png_bytes, text, ASK_VLM_AUTO_TIMEOUT_SEC)
    except SatqueryVlmError:
        started = time.perf_counter()
        try:
            narrated = _gemini_only_answer(text, png_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"Gemini fallback failed: {exc}",
            ) from exc
        return AskGroundedResponse(
            vlm_fact="",
            narrated_answer=narrated,
            model_chain=["gemini"],
            latency_sec=round(time.perf_counter() - started, 3),
            path_used="gemini",
        )
    narrated = _narrate_fact(text, fact, png_bytes)
    return AskGroundedResponse(
        vlm_fact=fact,
        narrated_answer=narrated,
        model_chain=["satquery-vlm", NARRATOR_MODEL],
        latency_sec=round(latency, 3),
        path_used="satquery-grounded",
    )

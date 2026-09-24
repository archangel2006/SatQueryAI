from __future__ import annotations

import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.i18n import elevenlabs
from app.i18n.elevenlabs import ElevenLabsError
from app.i18n.languages import is_demo_language
from app.i18n.translate import TranslationError, from_english, to_english
from app.llm.satquery_vlm import (
    ASK_VLM_AUTO_TIMEOUT_SEC,
    ASK_VLM_TIMEOUT_SEC,
    SatqueryVlmError,
    _gemini_only_answer,
    _narrate_fact,
    _png_from_form,
    query_vlm,
)
from app.schemas import AskLocaleResponse, SttResponse, TranslateResponse

router = APIRouter(tags=["ask-i18n"])


def _check_language(language: str) -> str:
    code = (language or "").strip().lower()
    if not is_demo_language(code):
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: en, hi, hinglish, ta, te, bn.",
        )
    return code


def _raise_eleven(exc: ElevenLabsError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/stt", response_model=SttResponse)
async def stt(
    audio: UploadFile = File(...),
    language: str = Form("hi"),
) -> SttResponse:
    code = _check_language(language)
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    try:
        text = await elevenlabs.speech_to_text(
            data, audio.filename or "speech.webm", code
        )
    except ElevenLabsError as exc:
        _raise_eleven(exc)
    return SttResponse(text=text)


async def _answer_english(
    mode: str,
    png_bytes: bytes,
    question_en: str,
) -> tuple[str, str, str, float]:
    if mode == "gemini":
        started = time.perf_counter()
        try:
            answer = _gemini_only_answer(question_en, png_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Gemini failed: {exc}") from exc
        return "", answer, "gemini", time.perf_counter() - started

    timeout = ASK_VLM_AUTO_TIMEOUT_SEC if mode == "auto" else ASK_VLM_TIMEOUT_SEC
    try:
        fact, latency = await query_vlm(png_bytes, question_en, timeout)
    except SatqueryVlmError as exc:
        if mode != "auto":
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        started = time.perf_counter()
        try:
            answer = _gemini_only_answer(question_en, png_bytes)
        except Exception as gemini_exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"Gemini fallback failed: {gemini_exc}",
            ) from gemini_exc
        return "", answer, "gemini", time.perf_counter() - started

    narrated = _narrate_fact(question_en, fact, png_bytes)
    return fact, narrated, "satquery-grounded", latency


@router.post("/ask_locale", response_model=AskLocaleResponse)
async def ask_locale(
    image: UploadFile = File(...),
    question: str = Form(...),
    language: str = Form("en"),
    mode: str = Form("satquery"),
) -> AskLocaleResponse:
    code = _check_language(language)
    chosen = (mode or "").strip().lower()
    if chosen not in ("satquery", "gemini", "auto"):
        raise HTTPException(
            status_code=400,
            detail="Mode must be satquery, gemini, or auto.",
        )
    png_bytes, user_text = await _png_from_form(image, question)
    try:
        question_en = to_english(user_text, code)
        fact, narrated, path_used, latency = await _answer_english(
            chosen, png_bytes, question_en
        )
        reply_text = from_english(narrated, code)
    except TranslationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AskLocaleResponse(
        user_text=user_text,
        question_en=question_en,
        vlm_fact=fact,
        reply_text=reply_text,
        path_used=path_used,
        latency_sec=round(latency, 3),
    )


@router.post("/translate", response_model=TranslateResponse)
async def translate(
    text: str = Form(...),
    language: str = Form("en"),
    direction: str = Form("to_en"),
) -> TranslateResponse:
    code = _check_language(language)
    source = (text or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="Text is required.")
    way = (direction or "").strip().lower()
    if way not in ("to_en", "from_en"):
        raise HTTPException(status_code=400, detail="Direction must be to_en or from_en.")
    try:
        translated = to_english(source, code) if way == "to_en" else from_english(source, code)
    except TranslationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return TranslateResponse(text=translated)


@router.post("/tts")
async def tts(text: str = Form(...), language: str = Form("hi")) -> Response:
    code = _check_language(language)
    spoken = (text or "").strip()
    if not spoken:
        raise HTTPException(status_code=400, detail="Text is required.")
    try:
        audio = await elevenlabs.text_to_speech(spoken, code)
    except ElevenLabsError as exc:
        _raise_eleven(exc)
    return Response(content=audio, media_type="audio/mpeg")

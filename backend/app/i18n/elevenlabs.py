from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.i18n.languages import tts_language_code

STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
STT_TIMEOUT_SEC = 60.0
TTS_TIMEOUT_SEC = 30.0


class ElevenLabsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _api_key() -> str:
    key = get_settings().elevenlabs_api_key.strip()
    if not key:
        raise ElevenLabsError(503, "ELEVENLABS_API_KEY is not configured.")
    return key


async def speech_to_text(audio: bytes, filename: str, language: str) -> str:
    key = _api_key()
    data = {"model_id": "scribe_v2", "language_code": tts_language_code(language)}
    files = {"file": (filename or "speech.webm", audio, "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT_SEC) as client:
            response = await client.post(
                STT_URL,
                headers={"xi-api-key": key},
                data=data,
                files=files,
            )
    except httpx.TimeoutException as exc:
        raise ElevenLabsError(504, "ElevenLabs speech-to-text timed out.") from exc
    except httpx.HTTPError as exc:
        raise ElevenLabsError(502, f"ElevenLabs speech-to-text unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise ElevenLabsError(
            502,
            f"ElevenLabs speech-to-text failed with HTTP {response.status_code}.",
        )
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise ElevenLabsError(502, "ElevenLabs speech-to-text returned non-JSON.") from exc
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ElevenLabsError(502, "ElevenLabs speech-to-text returned no text.")
    return text.strip()


async def text_to_speech(text: str, language: str) -> bytes:
    key = _api_key()
    voice_id = get_settings().elevenlabs_voice_id.strip()
    if not voice_id:
        raise ElevenLabsError(503, "ELEVENLABS_VOICE_ID is not configured.")
    model_id = get_settings().elevenlabs_tts_model.strip() or "eleven_v3"
    url = TTS_URL.format(voice_id=voice_id)
    body = {
        "text": text,
        "model_id": model_id,
        "language_code": tts_language_code(language),
    }
    try:
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT_SEC) as client:
            response = await client.post(
                url,
                headers={"xi-api-key": key, "Accept": "audio/mpeg"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise ElevenLabsError(504, "ElevenLabs text-to-speech timed out.") from exc
    except httpx.HTTPError as exc:
        raise ElevenLabsError(502, f"ElevenLabs text-to-speech unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise ElevenLabsError(
            502,
            f"ElevenLabs text-to-speech failed with HTTP {response.status_code}.",
        )
    if not response.content:
        raise ElevenLabsError(502, "ElevenLabs text-to-speech returned empty audio.")
    return response.content

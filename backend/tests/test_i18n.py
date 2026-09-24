from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.i18n import elevenlabs
from app.i18n.translate import TranslationError


async def _ok_vlm(*_args: Any, **_kwargs: Any) -> tuple[str, float]:
    return "Yes.", 0.5


def test_stt_missing_key(client: TestClient) -> None:
    res = client.post(
        "/stt",
        files={"audio": ("speech.webm", b"fake-audio", "audio/webm")},
        data={"language": "hi"},
    )
    assert res.status_code == 503
    assert "ELEVENLABS_API_KEY" in res.json()["detail"]


def test_tts_missing_key(client: TestClient) -> None:
    res = client.post("/tts", data={"text": "Haan.", "language": "hi"})
    assert res.status_code == 503
    assert "ELEVENLABS_API_KEY" in res.json()["detail"]


def test_ask_locale_english_skips_translate(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.i18n.router.query_vlm", _ok_vlm)
    res = client.post(
        "/ask_locale",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water?", "language": "en", "mode": "satquery"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_text"] == "Is there water?"
    assert body["question_en"] == "Is there water?"
    assert body["vlm_fact"] == "Yes."
    assert body["reply_text"] == "Yes."
    assert body["path_used"] == "satquery-grounded"


def test_ask_locale_non_english_without_gemini(
    client: TestClient, sample_png_bytes: bytes
) -> None:
    res = client.post(
        "/ask_locale",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "क्या पानी है?", "language": "hi", "mode": "satquery"},
    )
    assert res.status_code == 503
    assert "translation" in res.json()["detail"].lower()


def test_ask_locale_hindi_round_trip(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.i18n.router.query_vlm", _ok_vlm)

    def _to_en(text: str, language: str) -> str:
        assert language == "hi"
        assert text
        return "Is there water?"

    def _from_en(text: str, language: str) -> str:
        assert language == "hi"
        assert "Yes" in text
        return "हाँ, पानी है।"

    monkeypatch.setattr("app.i18n.router.to_english", _to_en)
    monkeypatch.setattr("app.i18n.router.from_english", _from_en)
    res = client.post(
        "/ask_locale",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "क्या पानी है?", "language": "hi", "mode": "satquery"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_text"] == "क्या पानी है?"
    assert body["question_en"] == "Is there water?"
    assert body["vlm_fact"] == "Yes."
    assert body["reply_text"] == "हाँ, पानी है।"
    assert body["path_used"] == "satquery-grounded"


def test_stt_success(client: TestClient, monkeypatch: Any) -> None:
    async def _stt(audio: bytes, filename: str, language: str) -> str:
        assert audio
        assert filename
        assert language == "hi"
        return "क्या पानी है?"

    monkeypatch.setattr(elevenlabs, "speech_to_text", _stt)
    res = client.post(
        "/stt",
        files={"audio": ("speech.webm", b"fake-audio", "audio/webm")},
        data={"language": "hi"},
    )
    assert res.status_code == 200
    assert res.json()["text"] == "क्या पानी है?"


def test_tts_success(client: TestClient, monkeypatch: Any) -> None:
    async def _tts(text: str, language: str) -> bytes:
        assert text == "हाँ"
        assert language == "hinglish"
        return b"mp3-bytes"

    monkeypatch.setattr(elevenlabs, "text_to_speech", _tts)
    res = client.post("/tts", data={"text": "हाँ", "language": "hinglish"})
    assert res.status_code == 200
    assert res.content == b"mp3-bytes"
    assert res.headers["content-type"].startswith("audio/mpeg")


def test_ask_locale_rejects_unknown_language(
    client: TestClient, sample_png_bytes: bytes
) -> None:
    res = client.post(
        "/ask_locale",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "water?", "language": "fr", "mode": "satquery"},
    )
    assert res.status_code == 400


def test_translate_english_skips(client: TestClient) -> None:
    res = client.post(
        "/translate",
        data={"text": "Where did water increase?", "language": "en", "direction": "to_en"},
    )
    assert res.status_code == 200
    assert res.json()["text"] == "Where did water increase?"


def test_translate_rejects_unknown_language(client: TestClient) -> None:
    res = client.post(
        "/translate",
        data={"text": "hello", "language": "fr", "direction": "from_en"},
    )
    assert res.status_code == 400


def test_translate_hinglish_error_shape() -> None:
    err = TranslationError(503, "Gemini is not configured for translation.")
    assert err.status_code == 503

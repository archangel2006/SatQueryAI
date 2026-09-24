from __future__ import annotations

from app.i18n.languages import language_name
from app.llm.gemini import FakeLLM, get_llm


class TranslationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _require_translator(language: str) -> None:
    if language == "en":
        return
    if isinstance(get_llm(), FakeLLM):
        raise TranslationError(
            503,
            "Gemini is not configured for translation.",
        )


def to_english(text: str, language: str) -> str:
    if language == "en":
        return text
    _require_translator(language)
    name = language_name(language)
    prompt = (
        f"Translate the following {name} question into English for a satellite-image model. "
        "Return only the English question. Do not add facts.\n\n"
        f"{text}"
    )
    try:
        translated = get_llm().answer([], prompt, None).strip()
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(502, f"Translation to English failed: {exc}") from exc
    return translated or text


def from_english(text: str, language: str) -> str:
    if language == "en":
        return text
    _require_translator(language)
    name = language_name(language)
    extra = ""
    if language == "hinglish":
        extra = (
            " Write in Hinglish: a natural mix of Hindi and English, the way people speak "
            "in India. Keep numbers exactly."
        )
    prompt = (
        f"Translate the following English satellite answer into {name}. "
        "Return only the translation. Do not add facts or numbers that are not in the English."
        f"{extra}\n\n{text}"
    )
    try:
        translated = get_llm().answer([], prompt, None).strip()
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(502, f"Translation from English failed: {exc}") from exc
    return translated or text

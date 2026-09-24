from __future__ import annotations

DEMO_LANGUAGES = ("en", "hi", "hinglish", "ta", "te", "bn")

_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "hinglish": "Hinglish (Hindi-English mix as spoken in India)",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
}


def is_demo_language(language: str) -> bool:
    return language in DEMO_LANGUAGES


def tts_language_code(language: str) -> str:
    """ElevenLabs has no Hinglish code; speak it with a Hindi voice."""
    if language == "hinglish":
        return "hi"
    return language


def language_name(language: str) -> str:
    return _NAMES.get(language, language)

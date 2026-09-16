from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.llm import satquery_vlm
from app.llm.gemini import set_llm
from app.llm.satquery_vlm import SatqueryVlmError


class _JsonResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


class _NarratorLLM:
    def answer(
        self,
        history: list[Any],
        user_message: str,
        image_png_bytes: bytes | None,
        grounding: str | None = None,
    ) -> str:
        assert "12 buildings" in user_message
        assert image_png_bytes
        return "The scene contains 12 buildings along the river."


async def _ok_vlm(
    png_bytes: bytes, question: str, timeout: float = 30.0
) -> tuple[str, float]:
    assert png_bytes.startswith(b"\x89PNG")
    assert question
    assert timeout > 0
    return "Yes.", 0.42


def test_ask_satquery_missing_url(client: TestClient, sample_png_bytes: bytes) -> None:
    res = client.post(
        "/ask_satquery",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water in this scene?"},
    )
    assert res.status_code == 503
    assert "SATQUERY_VLM_URL" in res.json()["detail"]


def test_ask_satquery_success(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    monkeypatch.setattr(satquery_vlm, "query_vlm", _ok_vlm)
    res = client.post(
        "/ask_satquery",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water in this scene?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "Yes."
    assert body["model"] == "satquery-vlm"
    assert body["latency_sec"] == 0.42


def test_ask_satquery_timeout(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    async def _timeout(*_args: Any, **_kwargs: Any) -> tuple[str, float]:
        raise SatqueryVlmError(504, "SatQuery VLM timed out.")

    monkeypatch.setattr(satquery_vlm, "query_vlm", _timeout)
    res = client.post(
        "/ask_satquery",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water?"},
    )
    assert res.status_code == 504


def test_ask_satquery_upstream_failure(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    async def _fail(*_args: Any, **_kwargs: Any) -> tuple[str, float]:
        raise SatqueryVlmError(502, "SatQuery VLM failed with HTTP 500.")

    monkeypatch.setattr(satquery_vlm, "query_vlm", _fail)
    res = client.post(
        "/ask_satquery",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water?"},
    )
    assert res.status_code == 502


def test_query_vlm_maps_httpx_timeout(monkeypatch: Any) -> None:
    monkeypatch.setattr(satquery_vlm, "_vlm_url", lambda: "http://vlm.test/query")

    async def _timeout(*_args: Any, **_kwargs: Any) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(satquery_vlm, "post_vlm", _timeout)

    async def _run() -> None:
        try:
            await satquery_vlm.query_vlm(b"png", "q", timeout=1.0)
        except SatqueryVlmError as exc:
            assert exc.status_code == 504
            return
        raise AssertionError("expected SatqueryVlmError")

    import asyncio

    asyncio.run(_run())


def test_query_vlm_maps_bad_status(monkeypatch: Any) -> None:
    monkeypatch.setattr(satquery_vlm, "_vlm_url", lambda: "http://vlm.test/query")
    monkeypatch.setattr(
        satquery_vlm,
        "post_vlm",
        AsyncMock(return_value=_JsonResponse({"error": "nope"}, status_code=500)),
    )

    async def _run() -> None:
        try:
            await satquery_vlm.query_vlm(b"png", "q")
        except SatqueryVlmError as exc:
            assert exc.status_code == 502
            return
        raise AssertionError("expected SatqueryVlmError")

    import asyncio

    asyncio.run(_run())


def test_ask_grounded_uses_fact_when_gemini_unavailable(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    async def _fact(*_args: Any, **_kwargs: Any) -> tuple[str, float]:
        return "Urban.", 1.2

    monkeypatch.setattr(satquery_vlm, "query_vlm", _fact)
    res = client.post(
        "/ask_grounded",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "What land cover is this?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["vlm_fact"] == "Urban."
    assert body["narrated_answer"] == "Urban."
    assert body["model_chain"] == ["satquery-vlm", "gemini-narrator"]
    assert body["path_used"] == "satquery-grounded"
    assert body["latency_sec"] == 1.2


def test_ask_grounded_narrates_with_gemini(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    async def _fact(*_args: Any, **_kwargs: Any) -> tuple[str, float]:
        return "12 buildings.", 0.8

    monkeypatch.setattr(satquery_vlm, "query_vlm", _fact)
    set_llm(_NarratorLLM())
    try:
        res = client.post(
            "/ask_grounded",
            files={"image": ("scene.png", sample_png_bytes, "image/png")},
            data={"question": "How many buildings?"},
        )
    finally:
        from app.llm.gemini import FakeLLM

        set_llm(FakeLLM())
    assert res.status_code == 200
    body = res.json()
    assert body["vlm_fact"] == "12 buildings."
    assert body["narrated_answer"] == "The scene contains 12 buildings along the river."
    assert body["path_used"] == "satquery-grounded"


def test_ask_auto_uses_vlm_when_available(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    monkeypatch.setattr(satquery_vlm, "query_vlm", _ok_vlm)
    res = client.post(
        "/ask_auto",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["vlm_fact"] == "Yes."
    assert body["narrated_answer"] == "Yes."
    assert body["path_used"] == "satquery-grounded"


def test_ask_auto_falls_back_to_gemini(
    client: TestClient, sample_png_bytes: bytes, monkeypatch: Any
) -> None:
    async def _fail(*_args: Any, **_kwargs: Any) -> tuple[str, float]:
        raise SatqueryVlmError(504, "SatQuery VLM timed out.")

    monkeypatch.setattr(satquery_vlm, "query_vlm", _fail)
    res = client.post(
        "/ask_auto",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "Is there water?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["path_used"] == "gemini"
    assert body["vlm_fact"] == ""
    assert "Is there water?" in body["narrated_answer"]
    assert body["model_chain"] == ["gemini"]


def test_ask_satquery_rejects_empty_question(
    client: TestClient, sample_png_bytes: bytes
) -> None:
    res = client.post(
        "/ask_satquery",
        files={"image": ("scene.png", sample_png_bytes, "image/png")},
        data={"question": "   "},
    )
    assert res.status_code == 400

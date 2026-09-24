from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FormatKind = Literal["geotiff", "raster"]
ModalityGuess = Literal["optical", "sar", "unknown"]
JobType = Literal["ask_scene", "before_after", "optical_sar"]


class ImageMetadata(BaseModel):
    width: int
    height: int
    band_count: int
    crs: str | None = None
    bounds: list[float] | None = None  # left, bottom, right, top
    modality_guess: ModalityGuess = "unknown"
    format_kind: FormatKind
    filename: str = ""


class PreviewResponse(BaseModel):
    preview_png_base64: str
    metadata: ImageMetadata


class CompatibilityResult(BaseModel):
    valid: bool
    error: str | None = None
    metadata: ImageMetadata | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class FusionResponse(BaseModel):
    text: str
    overlay_png_base64: str | None = None
    cloud_pct: float | None = None
    score: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class FusionFollowUpRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    specialist_summary: str = Field(min_length=1, max_length=12000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class FusionFollowUpResponse(BaseModel):
    text: str
    provider: str


class ChangeResponse(BaseModel):
    text: str
    overlay_png_base64: str | None = None
    score: float | None = None
    change_pct: float | None = None
    analysis_id: str
    evidence: dict


class AskSatqueryResponse(BaseModel):
    answer: str
    model: str
    latency_sec: float


class AskGroundedResponse(BaseModel):
    vlm_fact: str
    narrated_answer: str
    model_chain: list[str]
    latency_sec: float
    path_used: str


class SttResponse(BaseModel):
    text: str


class TranslateResponse(BaseModel):
    text: str


class AskLocaleResponse(BaseModel):
    user_text: str
    question_en: str
    vlm_fact: str
    reply_text: str
    path_used: str
    latency_sec: float

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat.router import router as chat_router
from app.compatibility.checker import check_compatibility
from app.config import get_settings
from app.db import init_db
from app.io.geotiff import preview_from_bytes
from app.llm.gemini import FakeLLM, get_llm
from app.schemas import ChangeResponse, CompatibilityResult, FusionResponse, JobType, PreviewResponse
from app.specialists.change_detection.change import configure_learned_change, run_change
from app.specialists.optical_sar.fusion import configure_learned_fusion, run_fusion
from fastapi import File, Form, HTTPException, UploadFile


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    checkpoint_path = Path(settings.fusion_checkpoint_path)
    if not checkpoint_path.is_absolute() and not checkpoint_path.is_file():
        workspace_path = Path(__file__).resolve().parents[2] / checkpoint_path
        if workspace_path.is_file():
            checkpoint_path = workspace_path
    configure_learned_fusion(str(checkpoint_path), settings.fusion_device)
    change_checkpoint_path = Path(settings.change_checkpoint_path)
    if not change_checkpoint_path.is_absolute() and not change_checkpoint_path.is_file():
        workspace_path = Path(__file__).resolve().parents[2] / change_checkpoint_path
        if workspace_path.is_file():
            change_checkpoint_path = workspace_path
    lc = configure_learned_change(str(change_checkpoint_path), settings.fusion_device)
    if lc.available:
        print(f"[change] SiameseChangeDetector loaded from {change_checkpoint_path}")
    else:
        print(f"[change] WARNING — model not loaded, using fallback. Reason: {lc.error}")
    yield


settings = get_settings()
app = FastAPI(title="SatQuery API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


def _gemini_fusion_wording(query: str | None, result: dict) -> str | None:
    """Use at most one Gemini call to explain already-computed fusion evidence."""
    if not query or not query.strip():
        return None
    llm = get_llm(settings)
    if isinstance(llm, FakeLLM):
        return None
    evidence = result.get("evidence", {})
    learned = evidence.get("learned_fusion", {})
    prompt = (
        "Answer the user's remote-sensing question using only the supplied specialist "
        "evidence. Do not invent locations, objects, percentages, or certainty. "
        "Mention when evidence is heuristic or insufficient. Keep the answer concise.\n\n"
        f"User question: {query.strip()}\n"
        f"Deterministic spatial evidence: {evidence}\n"
        f"Learned scene evidence: {learned}\n"
        f"Baseline result: {result.get('text', '')}"
    )
    try:
        answer = llm.answer([], prompt, None).strip()
    except Exception:
        return None
    return answer or None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/preview", response_model=PreviewResponse)
async def preview(file: UploadFile = File(...)) -> PreviewResponse:
    filename = file.filename or "upload.bin"
    data = await file.read()
    try:
        b64, meta = preview_from_bytes(data, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read image: {exc}") from exc
    return PreviewResponse(preview_png_base64=b64, metadata=meta)


@app.post("/compatibility", response_model=CompatibilityResult)
async def compatibility(
    job: JobType = Form(...),
    file: UploadFile | None = File(None),
    upload_files: list[UploadFile] | None = File(None, alias="files"),
) -> CompatibilityResult:
    input_files: list[tuple[str, bytes]] = []
    uploads = list(upload_files or [])
    if file is not None:
        uploads.insert(0, file)
    for upload in uploads:
        data = await upload.read()
        input_files.append((upload.filename or "upload.bin", data))
    return check_compatibility(job, input_files)


@app.post("/fusion", response_model=FusionResponse)
async def fusion(
    query: str | None = Form(None),
    upload_files: list[UploadFile] | None = File(None, alias="files"),
) -> FusionResponse:
    input_files: list[tuple[str, bytes]] = []
    for upload in upload_files or []:
        input_files.append((upload.filename or "upload.bin", await upload.read()))

    # The cloud workspace sends optical first and SAR second; use that explicit
    # UI contract when sparse raster metadata makes automatic guessing unreliable.
    compatibility_result = check_compatibility(
        "optical_sar",
        input_files,
        ordered_modalities=True,
    )
    if not compatibility_result.valid:
        raise HTTPException(status_code=400, detail=compatibility_result.error)

    try:
        result = run_fusion(
            input_files[0][1],
            input_files[1][1],
            query=query,
            metadata={"files": compatibility_result.extras.get("files", [])},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    wording = _gemini_fusion_wording(query, result)
    if wording:
        result["evidence"]["llm_wording"] = {"used": True, "provider": "gemini"}
        result["text"] = wording
    else:
        result["evidence"]["llm_wording"] = {"used": False}

    overlay = result.get("overlay")
    return FusionResponse(
        text=result["text"],
        overlay_png_base64=(base64.b64encode(overlay).decode("ascii") if overlay else None),
        cloud_pct=result.get("cloud_pct"),
        score=result.get("score"),
        evidence=result.get("evidence", {}),
    )


@app.post("/change", response_model=ChangeResponse)
async def change(
    query: str | None = Form(None),
    upload_files: list[UploadFile] | None = File(None, alias="files"),
) -> ChangeResponse:
    input_files = [
        (upload.filename or "upload.bin", await upload.read())
        for upload in upload_files or []
    ]
    compatibility_result = check_compatibility("before_after", input_files)
    if not compatibility_result.valid:
        raise HTTPException(status_code=400, detail=compatibility_result.error)
    try:
        result = run_change(
            input_files[0][1],
            input_files[1][1],
            query=query,
            metadata={"files": compatibility_result.extras.get("files", [])},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    overlay = result.get("overlay")
    return ChangeResponse(
        text=result["text"],
        overlay_png_base64=(base64.b64encode(overlay).decode("ascii") if overlay else None),
        score=result.get("score"),
        change_pct=result.get("change_pct"),
        evidence=result.get("evidence", {}),
    )

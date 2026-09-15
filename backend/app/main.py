from __future__ import annotations

import base64
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat.router import router as chat_router
from app.compatibility.checker import check_compatibility
from app.config import get_settings
from app.db import get_db, init_db
from app.io.geotiff import preview_from_bytes
from app.llm.gemini import FakeLLM, get_llm
from app.schemas import (
    ChangeResponse,
    CompatibilityResult,
    FusionFollowUpRequest,
    FusionFollowUpResponse,
    FusionResponse,
    JobType,
    PreviewResponse,
)
from app.specialists.change_detection.change import configure_learned_change, run_change
from app.specialists.optical_sar.fusion import (
    configure_learned_fusion,
    configure_water_segmentation,
    run_fusion,
)
from fastapi import File, Form, HTTPException, UploadFile
from app.models import Asset

from sqlalchemy.ext.asyncio import AsyncSession
from app.analysis.service import create_analysis
from app.auth import AuthUser, get_current_user
from app.chat.service import get_owned_session
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset

from app.storage.gcs import (
    ObjectStorage,
    analysis_overlay_object_key,
    get_storage,
)


from app.models import Analysis
from app.reports.service import create_analysis_report, save_report
from app.storage.gcs import analysis_overlay_object_key


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    checkpoint_path = Path(settings.fusion_checkpoint_path)
    if not checkpoint_path.is_absolute() and not checkpoint_path.is_file():
        workspace_path = Path(__file__).resolve().parents[2] / checkpoint_path
        if workspace_path.is_file():
            checkpoint_path = workspace_path
    configure_learned_fusion(str(checkpoint_path), settings.fusion_device)
    segmentation_checkpoint_path = Path(settings.water_segmentation_checkpoint_path)
    if not segmentation_checkpoint_path.is_absolute() and not segmentation_checkpoint_path.is_file():
        workspace_path = Path(__file__).resolve().parents[2] / segmentation_checkpoint_path
        if workspace_path.is_file():
            segmentation_checkpoint_path = workspace_path
    segmentation = configure_water_segmentation(
        str(segmentation_checkpoint_path), settings.water_segmentation_device
    )
    if segmentation.available:
        print(f"[water-segmentation] OpticalSarFusionSegmenter loaded from {segmentation_checkpoint_path}")
    else:
        print(f"[water-segmentation] WARNING — model not loaded. Reason: {segmentation.error}")
    change_checkpoint_path = Path(settings.change_checkpoint_path)
    if (
        not change_checkpoint_path.is_absolute()
        and not change_checkpoint_path.is_file()
    ):
        workspace_path = Path(__file__).resolve().parents[2] / change_checkpoint_path
        if workspace_path.is_file():
            change_checkpoint_path = workspace_path
    lc = configure_learned_change(str(change_checkpoint_path), settings.fusion_device)
    if lc.available:
        print(f"[change] SiameseChangeDetector loaded from {change_checkpoint_path}")
    else:
        print(
            f"[change] WARNING — model not loaded, using fallback. Reason: {lc.error}"
        )
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
    segmentation_active = bool(evidence.get("water_segmentation", {}).get("available"))
    learned = evidence.get("learned_fusion", {}) if not segmentation_active else {}
    hierarchy = (
        "The OpticalSarFusionSegmenter result is the primary pixel-level water evidence. "
        "State that result first. This model has no built-up head, so do not describe "
        "built-up coverage as a segmentation result. Do not call the model output heuristic "
        "or deterministic."
        if segmentation_active
        else "The specialist result is heuristic optical/SAR evidence; say so clearly."
    )
    prompt = (
        "Answer the user's remote-sensing question using only the supplied specialist "
        "evidence. Do not invent locations, objects, percentages, or certainty. "
        "Keep the answer concise. " + hierarchy + "\n\n"
        f"User question: {query.strip()}\n"
        f"Segmentation/specialist evidence: {evidence}\n"
        f"Legacy classifier evidence (only if supplied): {learned}\n"
        f"Specialist summary: {result.get('text', '')}"
    )
    try:
        answer = llm.answer([], prompt, None).strip()
    except Exception:
        return None
    # Gemini sometimes escapes Markdown emphasis/list markers even though the
    # frontend renders Markdown. Restore those markers for readable bullets.
    return re.sub(r"\\([*_])", r"\1", answer) or None


@app.post("/fusion/follow-up", response_model=FusionFollowUpResponse)
async def fusion_follow_up(request: FusionFollowUpRequest) -> FusionFollowUpResponse:
    """Answer a follow-up with Gemini, grounded in the prior model result."""
    llm = get_llm(settings)
    if isinstance(llm, FakeLLM):
        raise HTTPException(status_code=503, detail="Gemini is not configured for follow-up questions.")
    prompt = (
        "Answer the follow-up remote-sensing question using only this prior OpticalSarFusionSegmenter "
        "result and its evidence. The model is the primary water evidence. Do not invent new "
        "measurements or claim that built-up cues came from the water model. Keep the answer concise.\n\n"
        f"Prior specialist summary: {request.specialist_summary}\n"
        f"Prior evidence: {request.evidence}\n\n"
        f"Follow-up question: {request.query.strip()}"
    )
    try:
        answer = llm.answer([], prompt, None).strip()
    except Exception as exc:  # noqa: BLE001 - expose a useful API failure to the chat UI
        raise HTTPException(status_code=503, detail=f"Gemini follow-up failed: {exc}") from exc
    cleaned = re.sub(r"\\([*_])", r"\1", answer)
    if not cleaned:
        raise HTTPException(status_code=503, detail="Gemini returned an empty follow-up response.")
    return FusionFollowUpResponse(text=cleaned, provider="gemini")


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
        raise HTTPException(
            status_code=400, detail=f"Could not read image: {exc}"
        ) from exc
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
        allow_geospatial_alignment=True,
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
        overlay_png_base64=(
            base64.b64encode(overlay).decode("ascii") if overlay else None
        ),
        cloud_pct=result.get("cloud_pct"),
        score=result.get("score"),
        evidence=result.get("evidence", {}),
    )


@app.post("/change", response_model=ChangeResponse)
async def change(
    session_id: str = Form(...),
    query: str | None = Form(None),
    before_asset_id: str | None = Form(None),
    after_asset_id: str | None = Form(None),
    upload_files: list[UploadFile] | None = File(None, alias="files"),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
    storage: ObjectStorage = Depends(get_storage),
) -> ChangeResponse:
    # Make sure this session belongs to the signed-in user.
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid session ID",
        ) from exc

    await get_owned_session(
        db,
        session_uuid,
        user.clerk_user_id,
    )

    input_files = [
        (
            upload.filename or "upload.bin",
            await upload.read(),
        )
        for upload in upload_files or []
    ]

    compatibility_result = check_compatibility(
        "before_after",
        input_files,
    )

    if not compatibility_result.valid:
        raise HTTPException(
            status_code=400,
            detail=compatibility_result.error,
        )

    try:
        result = run_change(
            input_files[0][1],
            input_files[1][1],
            query=query,
            metadata={
                "files": compatibility_result.extras.get("files", []),
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    overlay = result.get("overlay")

    # Create the database record first so we have an analysis ID.
    analysis = await create_analysis(
        db,
        session_id=session_uuid,
        before_asset_id=uuid.UUID(before_asset_id) if before_asset_id else None,
        after_asset_id=uuid.UUID(after_asset_id) if after_asset_id else None,
        analysis_text=result["text"],
        change_pct=result.get("change_pct"),
        score=result.get("score"),
        method=result.get("evidence", {}).get("method"),
        evidence=result.get("evidence", {}),
    )

    # Save the generated overlay to object storage.
    overlay_gcs_uri = None

    if overlay:
        overlay_key = analysis_overlay_object_key(
            user.clerk_user_id,
            session_id,
            str(analysis.id),
        )

        overlay_gcs_uri = storage.upload_bytes(
            overlay_key,
            overlay,
            content_type="image/png",
        )

        analysis.overlay_gcs_uri = overlay_gcs_uri
        await db.commit()
        await db.refresh(analysis)

    return ChangeResponse(
        text=result["text"],
        overlay_png_base64=(
            base64.b64encode(overlay).decode("ascii") if overlay else None
        ),
        score=result.get("score"),
        change_pct=result.get("change_pct"),
        analysis_id=str(analysis.id),
        evidence={
            **result.get("evidence", {}),
            "analysis_id": str(analysis.id),
        },
    )


@app.post("/sessions/{session_id}/analyses/{analysis_id}/report")
async def generate_report(
    session_id: UUID,
    analysis_id: UUID,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
) -> dict:
    # Make sure the session belongs to the signed-in user.
    session = await get_owned_session(
        db,
        session_id,
        user.clerk_user_id,
    )

    # Find the requested analysis inside this session.
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.session_id == session_id,
        )
    )

    analysis = result.scalar_one_or_none()

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found",
        )

    # Load the generated overlay if one exists.

    before_png = None
    after_png = None
    overlay_png = None

    if analysis.before_asset_id:
        result = await db.execute(
            select(Asset).where(Asset.id == analysis.before_asset_id)
        )

        before_asset = result.scalar_one_or_none()

        if before_asset and before_asset.preview_gcs_uri:
            before_png = storage.download_bytes(before_asset.preview_gcs_uri)

    if analysis.after_asset_id:
        result = await db.execute(
            select(Asset).where(Asset.id == analysis.after_asset_id)
        )

        after_asset = result.scalar_one_or_none()

        if after_asset and after_asset.preview_gcs_uri:
            after_png = storage.download_bytes(after_asset.preview_gcs_uri)

    if analysis.overlay_gcs_uri:
        try:
            overlay_png = storage.download_bytes(analysis.overlay_gcs_uri)
        except FileNotFoundError:
            overlay_png = None

        if analysis.overlay_gcs_uri:
            try:
                overlay_png = storage.download_bytes(analysis.overlay_gcs_uri)
            except FileNotFoundError:
                overlay_png = None

    # Generate the PDF.
    pdf_bytes = create_analysis_report(
        title=f"{session.title} — Satellite Analysis",
        analysis_text=analysis.analysis_text,
        change_pct=analysis.change_pct,
        score=analysis.score,
        method=analysis.method,
        before_png=before_png,
        after_png=after_png,
        overlay_png=overlay_png,
    )

    # Store the PDF.
    report_id = uuid.uuid4()

    report_key = (
        f"users/{user.clerk_user_id}/sessions/" f"{session_id}/reports/{report_id}.pdf"
    )

    pdf_gcs_uri = storage.upload_bytes(
        report_key,
        pdf_bytes,
        content_type="application/pdf",
    )

    # Save report metadata.
    report = await save_report(
        db,
        session_id=session_id,
        analysis_id=analysis.id,
        title=f"{session.title} — Satellite Analysis",
        pdf_gcs_uri=pdf_gcs_uri,
    )

    return {
        "id": str(report.id),
        "session_id": str(report.session_id),
        "analysis_id": str(report.analysis_id),
        "title": report.title,
        "pdf_gcs_uri": report.pdf_gcs_uri,
        "created_at": report.created_at,
    }

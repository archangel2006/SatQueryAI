from __future__ import annotations

from typing import Annotated
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from app.auth.clerk import AuthUser, get_current_user
from app.chat import service
from app.config import Settings, get_settings
from app.db import get_db
from app.llm.gemini import ChatLLM, get_llm
from app.schemas_chat import (
    MessageCreate,
    MessageOut,
    SendMessageResponse,
    SessionCreate,
    SessionListItem,
    SessionOut,
    SessionUpdate,
    UploadAssetResponse,
)
from app.storage.gcs import ObjectStorage, get_storage
from app.analysis.service import list_analyses

from sqlalchemy import select
from app.models import Report

router = APIRouter(tags=["chat"])


def _storage() -> ObjectStorage:
    try:
        return get_storage()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Object storage unavailable: {exc}",
        ) from exc


def _llm() -> ChatLLM:
    return get_llm()


@router.post("/sessions", response_model=SessionOut)
async def create_session(
    body: SessionCreate,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionOut:
    session = await service.create_session(
        db, user.clerk_user_id, title=body.title, job_type=body.job_type
    )
    return SessionOut(
        id=session.id,
        title=session.title,
        job_type=session.job_type,
        created_at=session.created_at,
        updated_at=session.updated_at,
        assets=[],
    )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionListItem]:
    sessions = await service.list_sessions(db, user.clerk_user_id)
    return [service.session_to_list_item(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(_storage)],
) -> SessionOut:
    session = await service.get_owned_session(
        db, session_id, user.clerk_user_id, with_assets=True
    )
    return service.session_to_out(session, storage)


@router.patch("/sessions/{session_id}", response_model=SessionListItem)
async def rename_session(
    session_id: UUID,
    body: SessionUpdate,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionListItem:
    session = await service.update_session_title(
        db, session_id, user.clerk_user_id, body.title
    )
    return service.session_to_list_item(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(_storage)],
) -> None:
    await service.delete_session(db, storage, session_id, user.clerk_user_id)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(
    session_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(_storage)],
) -> list[MessageOut]:
    return await service.list_messages(db, storage, session_id, user.clerk_user_id)


@router.post("/sessions/{session_id}/assets", response_model=UploadAssetResponse)
async def upload_asset(
    session_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(_storage)],
    llm: Annotated[ChatLLM, Depends(_llm)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile = File(...),
    message: str | None = Form(None),
) -> UploadAssetResponse:
    data = await file.read()
    filename = file.filename or "upload.bin"
    return await service.upload_asset(
        db,
        storage,
        session_id,
        user.clerk_user_id,
        filename,
        data,
        message=message,
        llm=llm,
        settings=settings,
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def post_message(
    session_id: UUID,
    body: MessageCreate,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(_storage)],
    llm: Annotated[ChatLLM, Depends(_llm)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SendMessageResponse:
    return await service.send_message(
        db,
        storage,
        llm,
        settings,
        session_id,
        user.clerk_user_id,
        body.content,
    )


@router.get("/sessions/{session_id}/analyses")
async def get_analyses(
    session_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    # Verify that this session belongs to the signed-in user.
    await service.get_owned_session(
        db,
        session_id,
        user.clerk_user_id,
    )

    analyses = await list_analyses(
        db,
        session_id=session_id,
    )

    return [
        {
            "id": analysis.id,
            "session_id": analysis.session_id,
            "before_asset_id": analysis.before_asset_id,
            "after_asset_id": analysis.after_asset_id,
            "analysis_text": analysis.analysis_text,
            "change_pct": analysis.change_pct,
            "score": analysis.score,
            "method": analysis.method,
            "evidence": analysis.evidence,
            "overlay_gcs_uri": analysis.overlay_gcs_uri,
            "created_at": analysis.created_at,
        }
        for analysis in analyses
    ]


@router.get("/sessions/{session_id}/reports")
async def get_reports(
    session_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    await service.get_owned_session(
        db,
        session_id,
        user.clerk_user_id,
    )

    result = await db.execute(
        select(Report)
        .where(Report.session_id == session_id)
        .order_by(Report.created_at.desc())
    )

    reports = result.scalars().all()

    return [
        {
            "id": str(report.id),
            "session_id": str(report.session_id),
            "analysis_id": str(report.analysis_id),
            "title": report.title,
            "pdf_gcs_uri": report.pdf_gcs_uri,
            "created_at": report.created_at,
        }
        for report in reports
    ]


@router.get("/sessions/{session_id}/reports/{report_id}/download")
async def download_report(
    session_id: UUID,
    report_id: UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(_storage)],
) -> Response:
    await service.get_owned_session(
        db,
        session_id,
        user.clerk_user_id,
    )

    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.session_id == session_id,
        )
    )

    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report not found",
        )

    pdf_bytes = storage.download_bytes(
        report.pdf_gcs_uri,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="satellite-analysis-report.pdf"',
        },
    )

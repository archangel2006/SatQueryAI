from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.io.geotiff import preview_from_bytes
from app.llm.gemini import ChatLLM, ChatTurn
from app.llm.local_classifier import ClassificationResult, get_classifier
from app.models import Asset, ChatSession, Message
from app.schemas_chat import (
    AssetOut,
    MessageAttachmentOut,
    MessageOut,
    SendMessageResponse,
    SessionListItem,
    SessionOut,
    UploadAssetResponse,
)
from app.storage.gcs import (
    ObjectStorage,
    asset_object_key,
    guess_content_type,
    preview_object_key,
)


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _classify_scene(image_png_bytes: bytes | None) -> ClassificationResult | None:
    """Run the local scene/land-cover classifier, if a trained checkpoint is loaded.

    Never raises — a missing/unavailable classifier (no checkpoint trained yet,
    see train/README.md) just means no classification, not a broken upload.
    """
    if not image_png_bytes:
        return None
    try:
        classifier = get_classifier()
    except Exception:
        logger.exception("Failed to obtain scene classifier")
        return None
    if not classifier.available:
        return None
    result = classifier.classify(image_png_bytes)
    if result is not None:
        logger.info(
            "scene_classifier: label=%s confidence=%.3f topk=%s",
            result.label,
            result.confidence,
            result.topk,
        )
    return result


def _grounding_text(classification: ClassificationResult | None) -> str | None:
    if classification is None:
        return None
    return (
        f"An auxiliary land-cover classifier (ConvNeXt-tiny, fine-tuned on BigEarthNet) "
        f"predicts this scene is most likely '{classification.label}' "
        f"(confidence {classification.confidence:.0%})."
    )


_DEFAULT_CHANGE_TITLES = frozenset({"Before vs after"})
_DEFAULT_ASK_TITLES = frozenset({"New chat"})


def _maybe_auto_title_session(session: ChatSession, text: str) -> None:
    """Name the chat from the first real user question (Ask + Change)."""
    title = (session.title or "").strip()
    is_default_ask = title in _DEFAULT_ASK_TITLES
    is_default_change = title in _DEFAULT_CHANGE_TITLES
    if not (is_default_ask or is_default_change):
        return
    cleaned = text.strip()
    if not cleaned:
        return
    # Heal legacy change sessions that were stored as ask_scene.
    if is_default_change:
        session.job_type = "before_after"
    session.title = cleaned[:80]


async def create_session(
    db: AsyncSession,
    clerk_user_id: str,
    title: str = "New chat",
    job_type: str = "ask_scene",
) -> ChatSession:
    session = ChatSession(
        id=uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        title=title,
        job_type=job_type,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(db: AsyncSession, clerk_user_id: str) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.clerk_user_id == clerk_user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_owned_session(
    db: AsyncSession,
    session_id: UUID,
    clerk_user_id: str,
    *,
    with_assets: bool = False,
) -> ChatSession:
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    if with_assets:
        stmt = stmt.options(selectinload(ChatSession.assets))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if session.clerk_user_id != clerk_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your session.")
    return session


async def update_session_title(
    db: AsyncSession,
    session_id: UUID,
    clerk_user_id: str,
    title: str,
) -> ChatSession:
    session = await get_owned_session(db, session_id, clerk_user_id)
    session.title = title[:255]
    session.updated_at = _utcnow()
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(
    db: AsyncSession,
    storage: ObjectStorage,
    session_id: UUID,
    clerk_user_id: str,
) -> None:
    session = await get_owned_session(db, session_id, clerk_user_id, with_assets=True)
    prefix = f"users/{clerk_user_id}/sessions/{session_id}/"
    storage.delete_prefix(prefix)
    await db.delete(session)
    await db.commit()


def asset_to_out(asset: Asset, storage: ObjectStorage, *, include_preview: bool) -> AssetOut:
    preview_b64 = None
    if include_preview:
        try:
            preview_b64 = base64.b64encode(storage.download_bytes(asset.preview_gcs_uri)).decode(
                "ascii"
            )
        except FileNotFoundError:
            preview_b64 = None
    return AssetOut(
        id=asset.id,
        filename=asset.filename,
        content_type=asset.content_type,
        gcs_uri=asset.gcs_uri,
        preview_gcs_uri=asset.preview_gcs_uri,
        metadata=asset.metadata_json or {},
        preview_png_base64=preview_b64,
        created_at=asset.created_at,
    )


def session_to_out(session: ChatSession, storage: ObjectStorage) -> SessionOut:
    # Prefer already-eager-loaded assets; avoid async lazy IO.
    loaded = session.__dict__.get("assets", [])
    assets = [asset_to_out(a, storage, include_preview=True) for a in loaded]
    return SessionOut(
        id=session.id,
        title=session.title,
        job_type=session.job_type,
        created_at=session.created_at,
        updated_at=session.updated_at,
        assets=assets,
    )


def session_to_list_item(session: ChatSession) -> SessionListItem:
    return SessionListItem(
        id=session.id,
        title=session.title,
        job_type=session.job_type,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


async def list_messages(
    db: AsyncSession,
    storage: ObjectStorage,
    session_id: UUID,
    clerk_user_id: str,
) -> list[MessageOut]:
    await get_owned_session(db, session_id, clerk_user_id)
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .options(selectinload(Message.asset))
        .order_by(Message.created_at.asc())
    )
    messages = list(result.scalars().all())
    out: list[MessageOut] = []
    for msg in messages:
        attachment = None
        if msg.asset is not None:
            preview_b64 = None
            try:
                preview_b64 = base64.b64encode(
                    storage.download_bytes(msg.asset.preview_gcs_uri)
                ).decode("ascii")
            except FileNotFoundError:
                pass
            attachment = MessageAttachmentOut(
                id=msg.asset.id,
                filename=msg.asset.filename,
                preview_png_base64=preview_b64,
            )
        out.append(
            MessageOut(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                asset_id=msg.asset_id,
                attachment=attachment,
                created_at=msg.created_at,
            )
        )
    return out


async def upload_asset(
    db: AsyncSession,
    storage: ObjectStorage,
    session_id: UUID,
    clerk_user_id: str,
    filename: str,
    data: bytes,
    *,
    message: str | None = None,
    llm: ChatLLM | None = None,
    settings: Settings | None = None,
) -> UploadAssetResponse:
    session = await get_owned_session(db, session_id, clerk_user_id)
    try:
        preview_b64, metadata = preview_from_bytes(data, filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read image: {exc}",
        ) from exc

    asset_id = uuid.uuid4()
    original_key = asset_object_key(clerk_user_id, session_id, asset_id, filename)
    preview_key = preview_object_key(clerk_user_id, session_id, asset_id)
    content_type = guess_content_type(filename)
    preview_bytes = base64.b64decode(preview_b64)

    gcs_uri = storage.upload_bytes(original_key, data, content_type)
    preview_uri = storage.upload_bytes(preview_key, preview_bytes, "image/png")

    classification = _classify_scene(preview_bytes)
    metadata_dict = metadata.model_dump()
    if classification is not None:
        metadata_dict["scene_classification"] = {
            "label": classification.label,
            "confidence": classification.confidence,
            "topk": [{"label": label, "confidence": conf} for label, conf in classification.topk],
        }

    asset = Asset(
        id=asset_id,
        session_id=session_id,
        clerk_user_id=clerk_user_id,
        filename=filename,
        content_type=content_type,
        gcs_uri=gcs_uri,
        preview_gcs_uri=preview_uri,
        metadata_json=metadata_dict,
        created_at=_utcnow(),
    )

    question = (message or "").strip()
    if question:
        if llm is None or settings is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LLM is required when uploading with a message.",
            )
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(settings.chat_context_message_limit)
        )
        recent = list(reversed(list(result.scalars().all())))
        history = [
            ChatTurn(role=m.role, text=m.content)
            for m in recent
            if m.role in ("user", "assistant")
        ]
        user_msg = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            role="user",
            content=question,
            asset_id=asset_id,
            created_at=_utcnow(),
        )
        db.add(asset)
        db.add(user_msg)
        await db.flush()
        try:
            answer = llm.answer(history, question, preview_bytes, grounding=_grounding_text(classification))
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM failed: {exc}",
            ) from exc
        assistant_msg = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            role="assistant",
            content=answer,
            created_at=_utcnow(),
        )
        session.updated_at = _utcnow()
        if session.title == "New chat":
            session.title = question[:80]
        db.add(assistant_msg)
        await db.commit()
        await db.refresh(asset)
        await db.refresh(user_msg)
        await db.refresh(assistant_msg)
    else:
        user_msg = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            role="user",
            content="Use this scene",
            asset_id=asset_id,
            created_at=_utcnow(),
        )
        assistant_text = (
            "Got it — GeoTIFF loaded. Preview is on the right."
            if metadata.format_kind == "geotiff"
            else "Got it — benchmark image loaded (no CRS). Preview is on the right."
        )
        if classification is not None:
            assistant_text += (
                f" Detected scene type: {classification.label} ({classification.confidence:.0%})."
            )
        assistant_msg = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            role="assistant",
            content=assistant_text,
            created_at=_utcnow(),
        )
        session.updated_at = _utcnow()
        db.add_all([asset, user_msg, assistant_msg])
        await db.commit()
        await db.refresh(asset)
        await db.refresh(user_msg)
        await db.refresh(assistant_msg)

    asset_out = AssetOut(
        id=asset.id,
        filename=asset.filename,
        content_type=asset.content_type,
        gcs_uri=asset.gcs_uri,
        preview_gcs_uri=asset.preview_gcs_uri,
        metadata=asset.metadata_json or {},
        preview_png_base64=preview_b64,
        created_at=asset.created_at,
    )
    return UploadAssetResponse(
        asset=asset_out,
        user_message=MessageOut(
            id=user_msg.id,
            role=user_msg.role,
            content=user_msg.content,
            asset_id=asset.id,
            attachment=MessageAttachmentOut(
                id=asset.id,
                filename=asset.filename,
                preview_png_base64=preview_b64,
            ),
            created_at=user_msg.created_at,
        ),
        assistant_message=MessageOut(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            asset_id=None,
            attachment=None,
            created_at=assistant_msg.created_at,
        ),
    )

async def send_message(
    db: AsyncSession,
    storage: ObjectStorage,
    llm: ChatLLM,
    settings: Settings,
    session_id: UUID,
    clerk_user_id: str,
    content: str,
) -> SendMessageResponse:
    session = await get_owned_session(db, session_id, clerk_user_id, with_assets=True)
    text = content.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty message.")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(settings.chat_context_message_limit)
    )
    recent = list(reversed(list(result.scalars().all())))
    history = [ChatTurn(role=m.role, text=m.content) for m in recent if m.role in ("user", "assistant")]

    image_bytes: bytes | None = None
    assets = list(session.__dict__.get("assets", []) or [])
    if assets:
        latest = max(assets, key=lambda a: a.created_at)
        try:
            image_bytes = storage.download_bytes(latest.preview_gcs_uri)
        except FileNotFoundError:
            image_bytes = None

    user_msg = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role="user",
        content=text,
        created_at=_utcnow(),
    )
    db.add(user_msg)
    await db.flush()

    classification = _classify_scene(image_bytes)
    try:
        answer = llm.answer(history, text, image_bytes, grounding=_grounding_text(classification))
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM failed: {exc}",
        ) from exc

    assistant_msg = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        content=answer,
        created_at=_utcnow(),
    )
    session.updated_at = _utcnow()
    _maybe_auto_title_session(session, text)

    db.add(assistant_msg)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return SendMessageResponse(
        user_message=MessageOut(
            id=user_msg.id,
            role=user_msg.role,
            content=user_msg.content,
            asset_id=None,
            attachment=None,
            created_at=user_msg.created_at,
        ),
        assistant_message=MessageOut(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            asset_id=None,
            attachment=None,
            created_at=assistant_msg.created_at,
        ),
    )

# from __future__ import annotations

# import uuid
# from datetime import datetime

# from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
# from sqlalchemy.dialects.postgresql import JSONB
# from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.types import JSON, Uuid

# from app.db import Base

# # JSONB on Postgres; plain JSON elsewhere (e.g. SQLite tests).
# JsonType = JSON().with_variant(JSONB(), "postgresql")


# class ChatSession(Base):
#     __tablename__ = "chat_sessions"

#     id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     clerk_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
#     title: Mapped[str] = mapped_column(String(255), nullable=False, default="New chat")
#     job_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ask_scene")
#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now(), nullable=False
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )

#     messages: Mapped[list[Message]] = relationship(
#         back_populates="session",
#         cascade="all, delete-orphan",
#         order_by="Message.created_at",
#     )
#     assets: Mapped[list[Asset]] = relationship(
#         back_populates="session",
#         cascade="all, delete-orphan",
#     )


# class Asset(Base):
#     __tablename__ = "assets"

#     id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     session_id: Mapped[uuid.UUID] = mapped_column(
#         Uuid(as_uuid=True),
#         ForeignKey("chat_sessions.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )
#     clerk_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
#     filename: Mapped[str] = mapped_column(String(512), nullable=False)
#     content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
#     gcs_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
#     preview_gcs_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
#     metadata_json: Mapped[dict] = mapped_column("metadata", JsonType, nullable=False, default=dict)
#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now(), nullable=False
#     )

#     session: Mapped[ChatSession] = relationship(back_populates="assets")
#     messages: Mapped[list[Message]] = relationship(back_populates="asset")


# class Message(Base):
#     __tablename__ = "messages"
#     __table_args__ = (Index("ix_messages_session_created", "session_id", "created_at"),)

#     id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     session_id: Mapped[uuid.UUID] = mapped_column(
#         Uuid(as_uuid=True),
#         ForeignKey("chat_sessions.id", ondelete="CASCADE"),
#         nullable=False,
#     )
#     role: Mapped[str] = mapped_column(String(32), nullable=False)
#     content: Mapped[str] = mapped_column(Text, nullable=False)
#     asset_id: Mapped[uuid.UUID | None] = mapped_column(
#         Uuid(as_uuid=True),
#         ForeignKey("assets.id", ondelete="SET NULL"),
#         nullable=True,
#     )
#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now(), nullable=False
#     )

#     session: Mapped[ChatSession] = relationship(back_populates="messages")
#     asset: Mapped[Asset | None] = relationship(back_populates="messages")


from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    clerk_user_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New chat",
    )

    job_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="ask_scene",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    assets: Mapped[list[Asset]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Analysis.created_at",
    )

    reports: Mapped[list[Report]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Report.created_at",
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clerk_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="application/octet-stream",
    )

    gcs_uri: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    preview_gcs_uri: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JsonType,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship(
        back_populates="assets",
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="asset",
    )

    before_analyses: Mapped[list[Analysis]] = relationship(
        back_populates="before_asset",
        foreign_keys="Analysis.before_asset_id",
    )

    after_analyses: Mapped[list[Analysis]] = relationship(
        back_populates="after_asset",
        foreign_keys="Analysis.after_asset_id",
    )


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        Index(
            "ix_messages_session_created",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship(
        back_populates="messages",
    )

    asset: Mapped[Asset | None] = relationship(
        back_populates="messages",
    )


class Analysis(Base):
    __tablename__ = "analyses"

    __table_args__ = (
        Index(
            "ix_analyses_session_created",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    before_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    after_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    analysis_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    change_pct: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    score: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    method: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    evidence: Mapped[dict] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
    )

    overlay_gcs_uri: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship(
        back_populates="analyses",
    )

    before_asset: Mapped[Asset | None] = relationship(
        back_populates="before_analyses",
        foreign_keys=[before_asset_id],
    )

    after_asset: Mapped[Asset | None] = relationship(
        back_populates="after_analyses",
        foreign_keys=[after_asset_id],
    )

class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Satellite Analysis Report",
    )

    pdf_gcs_uri: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship(
        back_populates="reports",
    )

    analysis: Mapped[Analysis] = relationship()

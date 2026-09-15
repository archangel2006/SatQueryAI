from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Analysis


async def create_analysis(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    before_asset_id: uuid.UUID | None,
    after_asset_id: uuid.UUID | None,
    analysis_text: str,
    change_pct: float | None,
    score: float | None,
    method: str | None,
    evidence: dict,
) -> Analysis:
    analysis = Analysis(
        session_id=session_id,
        before_asset_id=before_asset_id,
        after_asset_id=after_asset_id,
        analysis_text=analysis_text,
        change_pct=change_pct,
        score=score,
        method=method,
        evidence=evidence,
    )

    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    return analysis


async def list_analyses(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
) -> list[Analysis]:
    result = await db.execute(
        select(Analysis)
        .where(Analysis.session_id == session_id)
        .order_by(Analysis.created_at.desc())
    )

    return list(result.scalars().all())
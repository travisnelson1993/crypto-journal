# app/services/analytics/discipline/persistence.py

from datetime import date
from typing import List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discipline_snapshot import DisciplineSnapshot


async def persist_discipline_snapshot(
    *,
    db: AsyncSession,
    snapshot_date: date,
    discipline_score: int,
    grade: str,
    summary: str,
    penalties: List[Dict[str, Any]],
    patterns: List[Dict[str, Any]],
    coaching_flags: List[str],
) -> DisciplineSnapshot:
    """
    Persist (or update) a daily discipline snapshot.

    Behavior:
    - One snapshot per day (idempotent by snapshot_date)
    - Advisory only (no trade blocking)
    - Overwrites existing snapshot for same date
    """

    # ---------------------------------------------------------
    # Check for existing snapshot for this date
    # ---------------------------------------------------------
    result = await db.execute(
        select(DisciplineSnapshot).where(
            DisciplineSnapshot.snapshot_date == snapshot_date
        )
    )

    existing = result.scalar_one_or_none()

    if existing:
        # -----------------------------------------------------
        # Update existing snapshot
        # -----------------------------------------------------
        existing.discipline_score = discipline_score
        existing.grade = grade
        existing.summary = summary
        existing.penalties = penalties
        existing.patterns = patterns
        existing.coaching_flags = coaching_flags

        await db.commit()
        await db.refresh(existing)

        return existing

    # ---------------------------------------------------------
    # Create new snapshot
    # ---------------------------------------------------------
    new_snapshot = DisciplineSnapshot(
        snapshot_date=snapshot_date,
        discipline_score=discipline_score,
        grade=grade,
        summary=summary,
        penalties=penalties,
        patterns=patterns,
        coaching_flags=coaching_flags,
    )

    db.add(new_snapshot)
    await db.commit()
    await db.refresh(new_snapshot)

    return new_snapshot

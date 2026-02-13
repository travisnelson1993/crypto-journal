from datetime import date
from typing import List, Dict, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
) -> Tuple[DisciplineSnapshot, str]:
    """
    Persist a daily discipline snapshot.

    - One snapshot per day (idempotent by snapshot_date)
    - Advisory only
    - Overwrites existing snapshot for the same date

    Returns:
        (snapshot, status)
        status: "created" | "updated"
    """

    # -------------------------------------------------
    # Check for existing snapshot for the day
    # -------------------------------------------------
    result = await db.execute(
        select(DisciplineSnapshot).where(
            DisciplineSnapshot.snapshot_date == snapshot_date
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.discipline_score = discipline_score
        existing.grade = grade
        existing.summary = summary
        existing.penalties = penalties
        existing.patterns = patterns
        existing.coaching_flags = coaching_flags

        await db.commit()
        await db.refresh(existing)

        return existing, "updated"

    # -------------------------------------------------
    # Create new snapshot
    # -------------------------------------------------
    snapshot = DisciplineSnapshot(
        snapshot_date=snapshot_date,
        discipline_score=discipline_score,
        grade=grade,
        summary=summary,
        penalties=penalties,
        patterns=patterns,
        coaching_flags=coaching_flags,
    )

    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return snapshot, "created"


from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.journal import DailyJournalEntry
from app.schemas.journal import DailyJournalCreate, DailyJournalOut


router = APIRouter(
    prefix="/api/journal/daily",
    tags=["journal"],
)


@router.post(
    "",
    response_model=DailyJournalOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_daily_journal(
    payload: DailyJournalCreate,
    db: AsyncSession = Depends(get_db),
):
    # 🔒 Enforce one entry per day
    result = await db.execute(
        select(DailyJournalEntry).where(
            DailyJournalEntry.date == payload.date
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Daily journal entry already exists for this date",
        )

    entry = DailyJournalEntry(**payload.model_dump())

    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return entry


@router.get(
    "/{entry_date}",
    response_model=DailyJournalOut,
)
async def get_daily_journal(
    entry_date: date,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DailyJournalEntry).where(
            DailyJournalEntry.date == entry_date
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily journal entry not found",
        )

    return entry


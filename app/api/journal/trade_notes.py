from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.trade import Trade
from app.models.journal import TradeNote
from app.schemas.journal import TradeNoteCreate, TradeNoteOut

router = APIRouter(
    prefix="/api/journal/trades",
    tags=["journal"]
)


@router.post(
    "/{trade_id}/notes",
    response_model=TradeNoteOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_trade_note(
    trade_id: int,
    payload: TradeNoteCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a trade note.
    Intended for:
    - Entry reasoning
    - Mid-trade deviations (ONLY if something changes)
    - Exit reasoning
    """

    # 🔎 Ensure trade exists
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    note = TradeNote(
        trade_id=trade_id,
        **payload.model_dump(),
    )

    db.add(note)
    await db.commit()
    await db.refresh(note)

    return note


@router.get(
    "/{trade_id}/notes",
    response_model=list[TradeNoteOut],
)
async def list_trade_notes(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch all notes for a trade (ordered).
    """

    result = await db.execute(
        select(TradeNote)
        .where(TradeNote.trade_id == trade_id)
        .order_by(TradeNote.created_at.asc())
    )

    return result.scalars().all()

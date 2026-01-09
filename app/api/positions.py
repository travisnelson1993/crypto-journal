# app/api/positions.py

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade
from app.services.position_builder import build_position_snapshot

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/")
async def get_positions(
    account_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Read-only derived endpoint.
    Builds current positions from trades.
    """

    stmt = select(Trade)
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)

    result = await db.execute(stmt)
    trades = result.scalars().all()

    grouped = defaultdict(list)

    for t in trades:
        key = (t.account_id, t.ticker, t.direction)
        grouped[key].append(t)

    positions = []

    for (_, _, _), trade_group in grouped.items():
        snapshot = build_position_snapshot(trade_group)

        positions.append(
            {
                "account_id": snapshot.account_id,
                "symbol": snapshot.symbol,
                "side": snapshot.side,
                "opened_qty": float(snapshot.opened_qty),
                "closed_qty": float(snapshot.closed_qty),
                "remaining_qty": float(snapshot.remaining_qty),
                "avg_entry_price": (
                    float(snapshot.avg_entry_price)
                    if snapshot.avg_entry_price is not None
                    else None
                ),
                "realized_pnl": float(snapshot.realized_pnl),
                "unrealized_pnl": (
                    float(snapshot.unrealized_pnl)
                    if snapshot.unrealized_pnl is not None
                    else None
                ),
                "opened_at": snapshot.opened_at,
                "closed_at": snapshot.closed_at,
            }
        )

    return positions


from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade
from app.services.trade_close import close_trade

# -------------------------------------------------
# Trades Router
# -------------------------------------------------
router = APIRouter(prefix="/api/trades", tags=["trades"])


# -------------------------------------------------
# Read-only lifecycle / ledger view
# -------------------------------------------------
@router.get("/lifecycle")
async def trade_lifecycle(db: AsyncSession = Depends(get_db)):
    """
    One row per trade (execution lifecycle view).
    This is an audit-style endpoint, not used for analytics.
    """

    stmt = select(Trade).order_by(Trade.entry_date.asc())
    result = await db.execute(stmt)
    trades = result.scalars().all()

    rows = []

    for t in trades:
        # ---------- STATUS ----------
        if t.end_date is None:
            if t.original_quantity > t.quantity:
                status = "PARTIAL"
            else:
                status = "OPEN"
        else:
            status = "CLOSED"

        # ---------- PNL ----------
        pnl_pct = t.realized_pnl_pct
        lev_pnl_pct = (
            pnl_pct * t.leverage
            if pnl_pct is not None and t.leverage is not None
            else None
        )

        rows.append(
            {
                "id": t.id,
                "ticker": t.ticker,
                "direction": t.direction,
                "entry_price": float(t.entry_price) if t.entry_price else None,
                "exit_price": float(t.exit_price) if t.exit_price else None,
                "entry_date": t.entry_date.isoformat() if t.entry_date else None,
                "end_date": t.end_date.isoformat() if t.end_date else None,
                "original_quantity": float(t.original_quantity),
                "quantity": float(t.quantity),
                "leverage": float(t.leverage) if t.leverage else 1.0,
                "status": status,
                "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
                "lev_pnl_pct": float(lev_pnl_pct) if lev_pnl_pct is not None else None,
                "risk_reward": None,  # computed in journal
            }
        )

    return rows


# -------------------------------------------------
# Trade close (mutation endpoint)
# -------------------------------------------------
class CloseTradeRequest(BaseModel):
    exit_price: Decimal = Field(..., gt=Decimal("0"))
    end_date: Optional[datetime] = None
    fee: Optional[Decimal] = None


@router.post("/{trade_id}/close")
async def close_trade_endpoint(
    trade_id: int,
    payload: CloseTradeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Close a trade and compute realized PnL immediately.
    This is the ONLY place realized PnL is written.
    """

    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.end_date is not None:
        raise HTTPException(status_code=400, detail="Trade already closed")

    close_trade(
        trade=trade,
        exit_price=payload.exit_price,
        closed_at=payload.end_date,
        fee=payload.fee,
    )

    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "original_quantity": float(trade.original_quantity),
        "entry_price": float(trade.entry_price),
        "exit_price": float(trade.exit_price),
        "entry_date": trade.entry_date.isoformat(),
        "end_date": trade.end_date.isoformat(),
        "realized_pnl": float(trade.realized_pnl),
        "realized_pnl_pct": float(trade.realized_pnl_pct),
        "leverage": float(trade.leverage or 1.0),
    }

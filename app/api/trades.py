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
    Audit-style endpoint. No analytics logic here.
    """

    stmt = select(Trade).order_by(Trade.entry_date.asc())
    result = await db.execute(stmt)
    trades = result.scalars().all()

    rows = []

    for t in trades:
        if t.end_date is None:
            status = "PARTIAL" if t.original_quantity > t.quantity else "OPEN"
        else:
            status = "CLOSED"

        pnl_pct = t.realized_pnl_pct
        lev = Decimal(str(t.leverage)) if t.leverage is not None else Decimal("1")
        lev_pnl_pct = pnl_pct * lev if pnl_pct is not None else None

        rows.append(
            {
                "id": t.id,
                "ticker": t.ticker,
                "direction": t.direction,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price) if t.exit_price else None,
                "entry_date": t.entry_date.isoformat(),
                "end_date": t.end_date.isoformat() if t.end_date else None,
                "original_quantity": float(t.original_quantity),
                "quantity": float(t.quantity),
                "leverage": float(lev),
                "status": status,
                "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
                "lev_pnl_pct": float(lev_pnl_pct) if lev_pnl_pct is not None else None,
                "risk_reward": None,
            }
        )

    return rows


# -------------------------------------------------
# Trade close
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
        "realized_pnl": float(trade.realized_pnl),
        "realized_pnl_pct": float(trade.realized_pnl_pct),
    }


# -------------------------------------------------
# Stop-loss update
# -------------------------------------------------
class UpdateStopLossRequest(BaseModel):
    stop_loss: Decimal = Field(..., gt=Decimal("0"))


@router.patch("/{trade_id}/stop-loss")
async def update_stop_loss(
    trade_id: int,
    payload: UpdateStopLossRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    trade.stop_loss = payload.stop_loss
    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "stop_loss": float(trade.stop_loss),
    }


# -------------------------------------------------
# Step 1.5 — Equity Snapshot (PATCH, immutable)
# -------------------------------------------------
class EquitySnapshotIn(BaseModel):
    account_equity_at_entry: Decimal = Field(..., gt=Decimal("0"))
    risk_usd_at_entry: Optional[Decimal] = Field(default=None, gt=Decimal("0"))


@router.patch("/{trade_id}/equity-snapshot")
async def set_equity_snapshot(
    trade_id: int,
    payload: EquitySnapshotIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Immutable equity snapshot at trade entry.
    """

    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.account_equity_at_entry is not None:
        raise HTTPException(
            status_code=409,
            detail="Equity snapshot already set for this trade",
        )

    equity = payload.account_equity_at_entry
    trade.account_equity_at_entry = equity

    risk_usd = payload.risk_usd_at_entry

    if risk_usd is None and trade.stop_loss is not None:
        risk_per_unit = (trade.entry_price - trade.stop_loss).copy_abs()
        risk_usd = risk_per_unit * trade.original_quantity
        if risk_usd == 0:
            risk_usd = None

    trade.risk_usd_at_entry = risk_usd
    trade.risk_pct_at_entry = (risk_usd / equity) if risk_usd else None

    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "account_equity_at_entry": float(trade.account_equity_at_entry),
        "risk_usd_at_entry": float(trade.risk_usd_at_entry) if trade.risk_usd_at_entry else None,
        "risk_pct_at_entry": float(trade.risk_pct_at_entry) if trade.risk_pct_at_entry else None,
        "note": "Equity snapshot stored (immutable)",
    }

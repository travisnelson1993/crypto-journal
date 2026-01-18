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
from app.api.analytics import position_sizing


# -------------------------------------------------
# Trades Router
# -------------------------------------------------
router = APIRouter(prefix="/api/trades", tags=["trades"])


# =================================================
# OPEN TRADE (ENTRY) — SOFT RISK WARNINGS ONLY
# =================================================
class OpenTradeRequest(BaseModel):
    ticker: str
    direction: str  # long / short
    entry_price: Decimal = Field(..., gt=Decimal("0"))
    quantity: Decimal = Field(..., gt=Decimal("0"))
    leverage: Optional[float] = 1.0
    entry_summary: Optional[str] = None
    source: Optional[str] = None


@router.post("")
async def open_trade(
    payload: OpenTradeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Open a trade.
    Risk engine runs in advisory mode ONLY.
    No blocking, warnings stored as metadata.
    """

    advisory = await position_sizing(db=db)

    risk_warnings = None

    if not advisory.get("trading_allowed", True):
        risk_warnings = {
            "timestamp": datetime.utcnow().isoformat(),
            "severity": "warning",
            "regime": advisory.get("regime"),
            "reasons": [advisory.get("notes")],
            "suggested_risk_pct": advisory.get("allowed_risk_pct"),
            "engine": "position_sizing_v1",
        }

    trade = Trade(
        ticker=payload.ticker,
        direction=payload.direction,
        entry_price=payload.entry_price,
        quantity=payload.quantity,
        original_quantity=payload.quantity,
        leverage=payload.leverage or 1.0,
        entry_date=datetime.utcnow(),
        entry_summary=payload.entry_summary,
        source=payload.source,
        risk_warnings=risk_warnings,
    )

    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "entry_price": float(trade.entry_price),
        "quantity": float(trade.quantity),
        "leverage": float(trade.leverage),
        "risk_warnings": trade.risk_warnings,
        "note": "Trade opened successfully",
    }


# =================================================
# READ-ONLY LIFECYCLE / LEDGER VIEW
# =================================================
@router.get("/lifecycle")
async def trade_lifecycle(db: AsyncSession = Depends(get_db)):
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
                "risk_warnings": t.risk_warnings,
            }
        )

    return rows


# =================================================
# READ SINGLE TRADE (DEBUG / UI)
# =================================================
@router.get("/{trade_id}")
async def get_trade(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "entry_price": float(trade.entry_price),
        "quantity": float(trade.quantity),
        "original_quantity": float(trade.original_quantity),
        "leverage": float(trade.leverage),
        "entry_date": trade.entry_date.isoformat(),
        "stop_loss": float(trade.stop_loss) if trade.stop_loss else None,
        "account_equity_at_entry": (
            float(trade.account_equity_at_entry)
            if trade.account_equity_at_entry
            else None
        ),
        "risk_usd_at_entry": (
            float(trade.risk_usd_at_entry)
            if trade.risk_usd_at_entry
            else None
        ),
        "risk_pct_at_entry": (
            float(trade.risk_pct_at_entry)
            if trade.risk_pct_at_entry
            else None
        ),
        "risk_warnings": trade.risk_warnings,
    }


# =================================================
# CLOSE TRADE
# =================================================
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


# =================================================
# STOP-LOSS UPDATE (recompute risk + advisories if equity exists)
# =================================================
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

    with db.no_autoflush:
        trade.stop_loss = payload.stop_loss

        # If equity snapshot exists, recompute risk metrics and advisories
        if trade.account_equity_at_entry:
            risk_per_unit = (trade.entry_price - trade.stop_loss).copy_abs()
            risk_usd = risk_per_unit * trade.original_quantity

            trade.risk_usd_at_entry = risk_usd if risk_usd > 0 else None
            trade.risk_pct_at_entry = (
                (trade.risk_usd_at_entry / trade.account_equity_at_entry)
                if trade.risk_usd_at_entry
                else None
            )

            from app.risk.advisories import compute_risk_advisories
            trade.risk_warnings = compute_risk_advisories(trade)

    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "stop_loss": float(trade.stop_loss),
        "risk_usd_at_entry": float(trade.risk_usd_at_entry)
        if trade.risk_usd_at_entry
        else None,
        "risk_pct_at_entry": float(trade.risk_pct_at_entry)
        if trade.risk_pct_at_entry
        else None,
        "risk_warnings": trade.risk_warnings,
    }


# =================================================
# STEP 1.5 — EQUITY SNAPSHOT (IMMUTABLE)
# =================================================
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
    Advisory-only risk evaluation occurs here.
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

    # -------------------------------------------------
    # Prevent premature autoflush (CRITICAL)
    # -------------------------------------------------
    with db.no_autoflush:

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

        # -------------------------------------------------
        # Recompute SOFT risk advisories (lifecycle-aware)
        # -------------------------------------------------
        from app.risk.advisories import compute_risk_advisories

        warnings = compute_risk_advisories(trade)
        trade.risk_warnings = warnings or None

    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "account_equity_at_entry": float(trade.account_equity_at_entry),
        "risk_usd_at_entry": float(trade.risk_usd_at_entry)
        if trade.risk_usd_at_entry
        else None,
        "risk_pct_at_entry": float(trade.risk_pct_at_entry)
        if trade.risk_pct_at_entry
        else None,
        "risk_warnings": trade.risk_warnings,
        "note": "Equity snapshot stored (immutable)",
    }

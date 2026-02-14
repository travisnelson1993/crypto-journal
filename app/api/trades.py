from datetime import datetime
from decimal import Decimal
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade
from app.services.trade_close import close_trade
from app.services.analytics.position_sizing import position_sizing
from app.risk.advisories import compute_risk_advisories
from app.schemas.trade_plan import TradePlanUpdate

from app.models.trade_entry_note import TradeEntryNote
from app.models.trade_exit_note import TradeExitNote
from app.models.trade_note import TradeNote
from app.models.trade_mindset_tag import TradeMindsetTag


router = APIRouter(prefix="/api/trades", tags=["trades"])


# -----------------------------
# Helpers
# -----------------------------
def fdec(x: Optional[Decimal]) -> Optional[float]:
    """Safe Decimal -> float (preserves 0)."""
    return float(x) if x is not None else None


def enum_to_str(x: Any) -> Any:
    """Safely convert Enum-like objects to their string value."""
    return x.value if hasattr(x, "value") else x


# =================================================
# OPEN TRADE (ENTRY) — SOFT ADVISORIES ONLY
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
    Advisory-only — never blocks execution.
    """

    advisory = await position_sizing(db=db)

    risk_warnings = None
    if not advisory.get("trading_allowed", True):
        risk_warnings = {
            "entry_advisory": [
                {
                    "code": "POSITION_SIZING_REDUCED",
                    "severity": "warning",
                    "metric": "risk_pct",
                    "allowed": advisory.get("allowed_risk_pct"),
                    "actual": None,
                    "message": advisory.get("notes"),
                    "engine": "position_sizing_v1",
                    "resolved": False,
                }
            ]
        }

    trade = Trade(
        ticker=payload.ticker,
        direction=payload.direction,
        entry_price=payload.entry_price,
        quantity=payload.quantity,
        original_quantity=payload.quantity,
        leverage=payload.leverage or 1.0,
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
        "entry_price": fdec(trade.entry_price),
        "quantity": fdec(trade.quantity),
        "leverage": float(trade.leverage),
        "risk_warnings": trade.risk_warnings,
        "note": "Trade opened successfully",
    }


# =================================================
# READ SINGLE TRADE (SAFE SERIALIZATION)
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
        "entry_price": fdec(trade.entry_price),
        "quantity": fdec(trade.quantity),
        "original_quantity": fdec(trade.original_quantity),
        "leverage": float(trade.leverage),
        "created_at": trade.created_at.isoformat(),
        "stop_loss": fdec(trade.stop_loss),
        "fee": fdec(trade.fee),
        "realized_pnl": fdec(trade.realized_pnl),
        "realized_pnl_pct": fdec(trade.realized_pnl_pct),
        "risk_warnings": trade.risk_warnings,
        "trade_plan": trade.trade_plan,
        "end_date": trade.end_date.isoformat() if trade.end_date is not None else None,
        "exit_price": fdec(trade.exit_price),
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
        "end_date": trade.end_date.isoformat() if trade.end_date is not None else None,
        "exit_price": fdec(trade.exit_price),
        "realized_pnl": fdec(trade.realized_pnl),
        "realized_pnl_pct": fdec(trade.realized_pnl_pct),
    }


# =================================================
# PRE-TRADE PLAN (INTENT ONLY — Category 3 Option A)
# =================================================
@router.patch("/{trade_id}/plan")
async def update_trade_plan(
    trade_id: int,
    payload: TradePlanUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.end_date is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot update plan on closed trade",
        )

    updates = payload.model_dump(exclude_unset=True)

    if (
        "planned_entry_price" in updates
        and "planned_stop_price" in updates
        and updates["planned_entry_price"] == updates["planned_stop_price"]
    ):
        raise HTTPException(
            status_code=400,
            detail="planned_entry_price and planned_stop_price cannot be equal",
        )

    trade.trade_plan = {**(trade.trade_plan or {}), **updates}

    await db.commit()
    await db.refresh(trade)

    return {
        "status": "ok",
        "trade_id": trade.id,
        "trade_plan": trade.trade_plan,
    }


# =================================================
# EQUITY SNAPSHOT (IMMUTABLE)
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
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.account_equity_at_entry is not None:
        raise HTTPException(
            status_code=409,
            detail="Equity snapshot already set for this trade",
        )

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

        warnings = compute_risk_advisories(trade)
        trade.risk_warnings = warnings or trade.risk_warnings

    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "account_equity_at_entry": fdec(trade.account_equity_at_entry),
        "risk_usd_at_entry": fdec(trade.risk_usd_at_entry),
        "risk_pct_at_entry": fdec(trade.risk_pct_at_entry),
        "risk_warnings": trade.risk_warnings,
        "note": "Equity snapshot stored (immutable)",
    }


# =================================================
# TRADE REFLECTION (Unified Retrieval — READ ONLY)
# =================================================
@router.get("/{trade_id}/reflection")
async def get_trade_reflection(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns complete reflection package for a trade:
    - Entry intent
    - Exit evaluation
    - Notes (entry/mid/exit)
    - Mindset tags
    """

    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    entry_note = (
        await db.execute(
            select(TradeEntryNote).where(TradeEntryNote.trade_id == trade_id)
        )
    ).scalar_one_or_none()

    exit_note = (
        await db.execute(
            select(TradeExitNote).where(TradeExitNote.trade_id == trade_id)
        )
    ).scalar_one_or_none()

    trade_notes = (
        await db.execute(
            select(TradeNote).where(TradeNote.trade_id == trade_id)
        )
    ).scalars().all()

    mindset_tags = (
        await db.execute(
            select(TradeMindsetTag)
            .join(TradeNote, TradeMindsetTag.trade_note_id == TradeNote.id)
            .where(TradeNote.trade_id == trade_id)
        )
    ).scalars().all()

    return {
        "trade_id": trade_id,
        "entry_note": {
            "strategy": entry_note.strategy,
            "planned_risk_pct": fdec(entry_note.planned_risk_pct),
            "confidence_at_entry": entry_note.confidence_at_entry,
            "entry_reasons": entry_note.entry_reasons,
            "optional_comment": entry_note.optional_comment,
            "created_at": entry_note.created_at.isoformat(),
        } if entry_note else None,
        "exit_note": {
            "exit_type": enum_to_str(exit_note.exit_type) if exit_note else None,
            "plan_followed": exit_note.plan_followed if exit_note else None,
            "violation_reason": enum_to_str(exit_note.violation_reason) if exit_note else None,
            "would_take_again": enum_to_str(exit_note.would_take_again) if exit_note else None,
            "created_at": exit_note.created_at.isoformat() if exit_note and exit_note.created_at else None,
        } if exit_note else None,
        "notes": [
            {
                "id": n.id,
                "note_type": enum_to_str(n.note_type),
                "content": n.content,
                "created_at": n.created_at.isoformat(),
            }
            for n in trade_notes
        ],
        "mindset_tags": [enum_to_str(tag.tag) for tag in mindset_tags],
    }

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

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
from app.models.trade_mindset_tag import TradeMindsetTag

# TradeNote is defined in app/models/journal.py (table: trade_notes)
from app.models.journal import TradeNote, TradeNoteType


router = APIRouter(prefix="/api/trades", tags=["trades"])


# =================================================
# Helpers
# =================================================
def _f(x):
    return float(x) if x is not None else None


async def _get_trade_or_404(db: AsyncSession, trade_id: int) -> Trade:
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


def _is_closed(trade: Trade) -> bool:
    # Source of truth for CLOSED state
    return trade.end_date is not None


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
        entry_date=datetime.utcnow(),  # keep if your Trade model has it
        entry_summary=payload.entry_summary,  # keep if your Trade model has it
        source=payload.source,  # keep if your Trade model has it
        risk_warnings=risk_warnings,
    )

    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "entry_price": _f(trade.entry_price),
        "quantity": _f(trade.quantity),
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
    trade = await _get_trade_or_404(db, trade_id)

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "entry_price": _f(trade.entry_price),
        "exit_price": _f(getattr(trade, "exit_price", None)),
        "quantity": _f(trade.quantity) if trade.quantity is not None else _f(trade.original_quantity),
        "original_quantity": _f(trade.original_quantity),
        "leverage": float(trade.leverage),
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "entry_date": trade.entry_date.isoformat() if getattr(trade, "entry_date", None) else None,
        "end_date": trade.end_date.isoformat() if trade.end_date else None,
        "stop_loss": _f(trade.stop_loss),
        "fee": _f(trade.fee),
        "realized_pnl": _f(trade.realized_pnl),
        "realized_pnl_pct": _f(trade.realized_pnl_pct),
        "risk_warnings": trade.risk_warnings,
        "trade_plan": trade.trade_plan,
        "entry_summary": getattr(trade, "entry_summary", None),
        "source": getattr(trade, "source", None),
        "account_equity_at_entry": _f(getattr(trade, "account_equity_at_entry", None)),
        "risk_usd_at_entry": _f(getattr(trade, "risk_usd_at_entry", None)),
        "risk_pct_at_entry": _f(getattr(trade, "risk_pct_at_entry", None)),
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
    trade = await _get_trade_or_404(db, trade_id)

    if _is_closed(trade):
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
        "end_date": trade.end_date.isoformat() if trade.end_date else None,
        "realized_pnl": _f(trade.realized_pnl),
        "realized_pnl_pct": _f(trade.realized_pnl_pct),
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
    trade = await _get_trade_or_404(db, trade_id)

    if _is_closed(trade):
        raise HTTPException(status_code=400, detail="Cannot update plan on closed trade")

    updates = payload.model_dump(exclude_unset=True)

    if (
        "planned_entry_price" in updates
        and "planned_stop_price" in updates
        and updates["planned_entry_price"] == updates["planned_stop_price"]
    ):
        raise HTTPException(status_code=400, detail="planned_entry_price and planned_stop_price cannot be equal")

    trade.trade_plan = {**(trade.trade_plan or {}), **updates}

    await db.commit()
    await db.refresh(trade)

    return {"status": "ok", "trade_id": trade.id, "trade_plan": trade.trade_plan}


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
    trade = await _get_trade_or_404(db, trade_id)

    if getattr(trade, "account_equity_at_entry", None) is not None:
        raise HTTPException(status_code=409, detail="Equity snapshot already set for this trade")

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
        "account_equity_at_entry": _f(trade.account_equity_at_entry),
        "risk_usd_at_entry": _f(trade.risk_usd_at_entry),
        "risk_pct_at_entry": _f(trade.risk_pct_at_entry),
        "risk_warnings": trade.risk_warnings,
        "note": "Equity snapshot stored (immutable)",
    }


# =================================================
# ENTRY NOTE (ONLY BEFORE CLOSE) — Upsert Allowed
# =================================================
class EntryNoteRequest(BaseModel):
    user_id: UUID
    entry_reasons: Dict[str, Any] = Field(default_factory=dict)
    strategy: Optional[str] = None
    planned_risk_pct: Optional[Decimal] = None
    confidence_at_entry: Optional[int] = Field(default=None, ge=1, le=10)
    optional_comment: Optional[str] = None


@router.post("/{trade_id}/entry-note")
async def upsert_entry_note(
    trade_id: int,
    payload: EntryNoteRequest,
    db: AsyncSession = Depends(get_db),
):
    trade = await _get_trade_or_404(db, trade_id)

    if _is_closed(trade):
        raise HTTPException(status_code=400, detail="Entry note can only be saved before the trade is closed")

    existing = (
        await db.execute(select(TradeEntryNote).where(TradeEntryNote.trade_id == trade_id))
    ).scalar_one_or_none()

    if existing:
        existing.entry_reasons = payload.entry_reasons
        existing.strategy = payload.strategy
        existing.planned_risk_pct = payload.planned_risk_pct
        existing.confidence_at_entry = payload.confidence_at_entry
        existing.optional_comment = payload.optional_comment
        await db.commit()
        await db.refresh(existing)
        return {"status": "updated", "trade_id": trade_id}

    note = TradeEntryNote(
        trade_id=trade_id,
        user_id=payload.user_id,
        entry_reasons=payload.entry_reasons,
        strategy=payload.strategy,
        planned_risk_pct=payload.planned_risk_pct,
        confidence_at_entry=payload.confidence_at_entry,
        optional_comment=payload.optional_comment,
    )
    db.add(note)
    await db.commit()
    return {"status": "created", "trade_id": trade_id}


# =================================================
# EXIT NOTE (ONLY AFTER CLOSE) — Upsert Allowed
# =================================================
class ExitNoteRequest(BaseModel):
    user_id: UUID
    exit_type: str  # tp | sl | manual | early
    plan_followed: int = Field(..., ge=0, le=1)
    violation_reason: Optional[str] = None  # fomo | loss_aversion | doubt | impatience
    would_take_again: Optional[str] = None  # yes | no | with_changes


@router.post("/{trade_id}/exit-note")
async def upsert_exit_note(
    trade_id: int,
    payload: ExitNoteRequest,
    db: AsyncSession = Depends(get_db),
):
    trade = await _get_trade_or_404(db, trade_id)

    if not _is_closed(trade):
        raise HTTPException(status_code=400, detail="Exit note can only be saved after the trade is closed")

    existing = (
        await db.execute(select(TradeExitNote).where(TradeExitNote.trade_id == trade_id))
    ).scalar_one_or_none()

    if existing:
        existing.exit_type = payload.exit_type
        existing.plan_followed = payload.plan_followed
        existing.violation_reason = payload.violation_reason
        existing.would_take_again = payload.would_take_again
        await db.commit()
        await db.refresh(existing)
        return {"status": "updated", "trade_id": trade_id}

    note = TradeExitNote(
        trade_id=trade_id,
        user_id=payload.user_id,
        exit_type=payload.exit_type,
        plan_followed=payload.plan_followed,
        violation_reason=payload.violation_reason,
        would_take_again=payload.would_take_again,
    )
    db.add(note)
    await db.commit()
    return {"status": "created", "trade_id": trade_id}


# =================================================
# TRADE NOTES (APPEND-ONLY)
# - mid: anytime
# - entry: only before close
# - exit: only after close
# =================================================
class TradeNoteRequest(BaseModel):
    note_type: TradeNoteType
    content: str = Field(..., min_length=1)


@router.post("/{trade_id}/notes")
async def add_trade_note(
    trade_id: int,
    payload: TradeNoteRequest,
    db: AsyncSession = Depends(get_db),
):
    trade = await _get_trade_or_404(db, trade_id)

    if payload.note_type == TradeNoteType.entry and _is_closed(trade):
        raise HTTPException(status_code=400, detail="Entry-type notes require an open trade")
    if payload.note_type == TradeNoteType.exit and not _is_closed(trade):
        raise HTTPException(status_code=400, detail="Exit-type notes require a closed trade")

    note = TradeNote(
        trade_id=trade_id,
        note_type=payload.note_type,
        content=payload.content,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return {
        "status": "created",
        "trade_id": trade_id,
        "note": {
            "id": note.id,
            "note_type": note.note_type,
            "content": note.content,
            "created_at": note.created_at.isoformat(),
        },
    }


# =================================================
# MINDSET TAG (APPEND-ONLY)
# =================================================
class MindsetTagRequest(BaseModel):
    trade_note_id: int
    tag: str  # must match TradeMindsetTagType enum values


@router.post("/{trade_id}/mindset-tags")
async def add_mindset_tag(
    trade_id: int,
    payload: MindsetTagRequest,
    db: AsyncSession = Depends(get_db),
):
    # Ensure note belongs to this trade (prevents tagging random notes)
    note = (
        await db.execute(select(TradeNote).where(TradeNote.id == payload.trade_note_id))
    ).scalar_one_or_none()

    if not note or note.trade_id != trade_id:
        raise HTTPException(status_code=404, detail="Trade note not found for this trade")

    tag_row = TradeMindsetTag(
        trade_note_id=payload.trade_note_id,
        tag=payload.tag,
    )
    db.add(tag_row)
    await db.commit()
    await db.refresh(tag_row)

    return {
        "status": "created",
        "trade_id": trade_id,
        "tag": tag_row.tag,
        "trade_note_id": tag_row.trade_note_id,
    }


# =================================================
# TRADE REFLECTION (READ ONLY)
# =================================================
@router.get("/{trade_id}/reflection")
async def get_trade_reflection(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    trade = await _get_trade_or_404(db, trade_id)

    entry_note = (
        await db.execute(select(TradeEntryNote).where(TradeEntryNote.trade_id == trade_id))
    ).scalar_one_or_none()

    exit_note = (
        await db.execute(select(TradeExitNote).where(TradeExitNote.trade_id == trade_id))
    ).scalar_one_or_none()

    trade_notes = (
        await db.execute(select(TradeNote).where(TradeNote.trade_id == trade_id).order_by(TradeNote.created_at.asc()))
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
        "closed": _is_closed(trade),
        "entry_note": (
            {
                "strategy": entry_note.strategy,
                "planned_risk_pct": _f(entry_note.planned_risk_pct) if entry_note.planned_risk_pct is not None else None,
                "confidence_at_entry": entry_note.confidence_at_entry,
                "entry_reasons": entry_note.entry_reasons,
                "optional_comment": entry_note.optional_comment,
                "created_at": entry_note.created_at.isoformat(),
            }
            if entry_note
            else None
        ),
        "exit_note": (
            {
                "exit_type": exit_note.exit_type,
                "plan_followed": exit_note.plan_followed,
                "violation_reason": exit_note.violation_reason,
                "would_take_again": exit_note.would_take_again,
                "created_at": exit_note.created_at.isoformat(),
            }
            if exit_note
            else None
        ),
        "notes": [
            {
                "id": n.id,
                "note_type": n.note_type,
                "content": n.content,
                "created_at": n.created_at.isoformat(),
            }
            for n in trade_notes
        ],
        "mindset_tags": [
            {"trade_note_id": t.trade_note_id, "tag": t.tag, "created_at": t.created_at.isoformat()}
            for t in mindset_tags
        ],
    }

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("")
async def journal_rows(db: AsyncSession = Depends(get_db)):
    """
    One row per CLOSED trade (journal-style).
    Matches:
    STATUS | PNL (%) | LEV PNL (%) | RISK-REWARD
    """

    status_expr = case(
        (Trade.realized_pnl > 0, "PROFIT"),
        (Trade.realized_pnl < 0, "LOSS"),
        else_="BREAKEVEN",
    )

    lev_pnl_pct_expr = Trade.realized_pnl_pct * func.nullif(Trade.leverage, 0)

    risk_usd_expr = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )
    rr_expr = Trade.realized_pnl / func.nullif(risk_usd_expr, 0)

    stmt = (
        select(
            Trade.id,
            Trade.ticker,
            Trade.direction,
            Trade.entry_date,
            Trade.end_date,
            status_expr.label("status"),
            Trade.realized_pnl_pct.label("pnl_pct"),
            lev_pnl_pct_expr.label("lev_pnl_pct"),
            rr_expr.label("risk_reward"),
        )
        .where(Trade.end_date.isnot(None))
        .order_by(Trade.end_date.desc())
    )

    rows = (await db.execute(stmt)).all()

    def f(x):
        return float(x) if x is not None else None

    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "direction": r.direction,
            "entry_date": r.entry_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "status": r.status,
            "pnl_pct": f(r.pnl_pct),
            "lev_pnl_pct": f(r.lev_pnl_pct),
            "risk_reward": f(r.risk_reward),
        }
        for r in rows
    ]


@router.get("/monthly")
async def journal_monthly(db: AsyncSession = Depends(get_db)):
    """
    Monthly performance summary (professional-grade).
    """

    month = func.date_trunc("month", Trade.end_date).label("month")

    wins = func.sum(case((Trade.realized_pnl > 0, 1), else_=0))
    losses = func.sum(case((Trade.realized_pnl < 0, 1), else_=0))
    trades = func.count()

    pnl_pct = Trade.realized_pnl_pct
    lev_pnl_pct = pnl_pct * func.nullif(Trade.leverage, 0)

    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )
    rr = Trade.realized_pnl / func.nullif(risk_usd, 0)

    stmt = (
        select(
            month,
            trades.label("trades"),
            wins.label("wins"),
            losses.label("losses"),
            (wins / func.nullif((wins + losses), 0) * 100).label("win_rate_pct"),
            (func.sum(pnl_pct) * 100).label("gains_pct"),
            (func.avg(pnl_pct) * 100).label("avg_return_pct"),
            (func.sum(lev_pnl_pct) * 100).label("lev_gains_pct"),
            (func.avg(lev_pnl_pct) * 100).label("avg_return_lev_pct"),
            func.sum(rr).label("total_rr"),
            func.avg(rr).label("avg_rr"),
            (func.max(pnl_pct) * 100).label("largest_win_pct"),
            (func.max(lev_pnl_pct) * 100).label("largest_lev_pct"),
            func.max(rr).label("largest_rr_win"),
        )
        .where(Trade.end_date.isnot(None))
        .group_by(month)
        .order_by(month.desc())
    )

    rows = (await db.execute(stmt)).all()

    def f(x):
        return float(x) if x is not None else None

    return [
        {
            "month": r.month.date().isoformat(),
            "trades": r.trades,
            "wins": int(r.wins or 0),
            "losses": int(r.losses or 0),
            "win_rate_pct": f(r.win_rate_pct),
            "gains_pct": f(r.gains_pct),
            "avg_return_pct": f(r.avg_return_pct),
            "lev_gains_pct": f(r.lev_gains_pct),
            "avg_return_lev_pct": f(r.avg_return_lev_pct),
            "total_rr": f(r.total_rr),
            "avg_rr": f(r.avg_rr),
            "largest_win_pct": f(r.largest_win_pct),
            "largest_lev_pct": f(r.largest_lev_pct),
            "largest_rr_win": f(r.largest_rr_win),
        }
        for r in rows
    ]

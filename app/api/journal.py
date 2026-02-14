from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

router = APIRouter(prefix="/api/journal", tags=["journal"])


# =================================================
# JOURNAL ROWS (ONE ROW PER CLOSED POSITION)
# =================================================
@router.get("")
async def journal_rows(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    One row per CLOSED trade (journal-style).
    Supports optional date and symbol filtering.
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

    filters = [
        Trade.end_date.isnot(None),
        Trade.entry_price.isnot(None),
    ]

    if start_date:
        filters.append(Trade.end_date >= start_date)

    if end_date:
        filters.append(Trade.end_date <= end_date)

    if ticker:
        filters.append(Trade.ticker == ticker)

    stmt = (
        select(
            Trade.id,
            Trade.ticker,
            Trade.direction,
            Trade.created_at.label("entry_date"),
            Trade.end_date,
            status_expr.label("status"),
            Trade.realized_pnl_pct.label("pnl_pct"),
            lev_pnl_pct_expr.label("lev_pnl_pct"),
            rr_expr.label("risk_reward"),
        )
        .where(*filters)
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


# =================================================
# MONTHLY PERFORMANCE SUMMARY
# =================================================
@router.get("/monthly")
async def journal_monthly(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Monthly performance summary (professional-grade).
    Supports optional date and symbol filtering.
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

    filters = [
        Trade.end_date.isnot(None),
        Trade.entry_price.isnot(None),
    ]

    if start_date:
        filters.append(Trade.end_date >= start_date)

    if end_date:
        filters.append(Trade.end_date <= end_date)

    if ticker:
        filters.append(Trade.ticker == ticker)

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
        .where(*filters)
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


# =================================================
# GLOBAL PERFORMANCE SUMMARY (ALL-TIME)
# =================================================
@router.get("/summary")
async def journal_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Global performance summary across CLOSED trades.
    Supports optional date and symbol filtering.
    """

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

    filters = [
        Trade.end_date.isnot(None),
        Trade.entry_price.isnot(None),
    ]

    if start_date:
        filters.append(Trade.end_date >= start_date)

    if end_date:
        filters.append(Trade.end_date <= end_date)

    if ticker:
        filters.append(Trade.ticker == ticker)

    stmt = (
        select(
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
        .where(*filters)
    )

    row = (await db.execute(stmt)).one()

    def f(x):
        return float(x) if x is not None else None

    return {
        "trades": int(row.trades or 0),
        "wins": int(row.wins or 0),
        "losses": int(row.losses or 0),
        "win_rate_pct": f(row.win_rate_pct),
        "gains_pct": f(row.gains_pct),
        "avg_return_pct": f(row.avg_return_pct),
        "lev_gains_pct": f(row.lev_gains_pct),
        "avg_return_lev_pct": f(row.avg_return_lev_pct),
        "total_rr": f(row.total_rr),
        "avg_rr": f(row.avg_rr),
        "largest_win_pct": f(row.largest_win_pct),
        "largest_lev_pct": f(row.largest_lev_pct),
        "largest_rr_win": f(row.largest_rr_win),
    }


@router.get("/expectancy")
async def journal_expectancy(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Expectancy calculation based on R-multiples.
    """

    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_expr = Trade.realized_pnl / func.nullif(risk_usd, 0)

    filters = [
        Trade.end_date.isnot(None),
        Trade.entry_price.isnot(None),
    ]

    if start_date:
        filters.append(Trade.end_date >= start_date)

    if end_date:
        filters.append(Trade.end_date <= end_date)

    if ticker:
        filters.append(Trade.ticker == ticker)

    stmt = (
        select(
            func.count().label("total"),
            func.sum(case((Trade.realized_pnl > 0, 1), else_=0)).label("wins"),
            func.sum(case((Trade.realized_pnl < 0, 1), else_=0)).label("losses"),
            func.avg(case((Trade.realized_pnl > 0, r_expr), else_=None)).label("avg_win_r"),
            func.avg(case((Trade.realized_pnl < 0, r_expr), else_=None)).label("avg_loss_r"),
        )
        .where(*filters)
    )

    row = (await db.execute(stmt)).one()

    total = row.total or 0
    wins = row.wins or 0
    losses = row.losses or 0

    win_rate = (wins / total) if total else 0
    avg_win_r = row.avg_win_r or 0
    avg_loss_r = abs(row.avg_loss_r or 0)

    expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)

    return {
        "total_trades": total,
        "win_rate": float(win_rate),
        "avg_win_r": float(avg_win_r),
        "avg_loss_r": float(avg_loss_r),
        "expectancy_r": float(expectancy),
    }


@router.get("/r-distribution")
async def journal_r_distribution(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    R-multiple distribution analytics.
    """

    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_expr = Trade.realized_pnl / func.nullif(risk_usd, 0)

    filters = [
        Trade.end_date.isnot(None),
        Trade.entry_price.isnot(None),
    ]

    if start_date:
        filters.append(Trade.end_date >= start_date)

    if end_date:
        filters.append(Trade.end_date <= end_date)

    if ticker:
        filters.append(Trade.ticker == ticker)

    stmt = (
        select(r_expr.label("r_value"))
        .where(*filters)
    )

    rows = (await db.execute(stmt)).all()

    r_values = [float(r.r_value) for r in rows if r.r_value is not None]

    if not r_values:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "std_dev": 0.0,
            "min_r": 0.0,
            "max_r": 0.0,
            "values": [],
        }

    import statistics

    return {
        "count": len(r_values),
        "mean": float(statistics.mean(r_values)),
        "median": float(statistics.median(r_values)),
        "std_dev": float(statistics.pstdev(r_values)) if len(r_values) > 1 else 0.0,
        "min_r": float(min(r_values)),
        "max_r": float(max(r_values)),
        "values": r_values,
    }


@router.get("/drawdown")
async def journal_drawdown(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    R-based equity curve and drawdown analytics.
    """

    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_expr = Trade.realized_pnl / func.nullif(risk_usd, 0)

    filters = [
        Trade.end_date.isnot(None),
        Trade.entry_price.isnot(None),
    ]

    if start_date:
        filters.append(Trade.end_date >= start_date)

    if end_date:
        filters.append(Trade.end_date <= end_date)

    if ticker:
        filters.append(Trade.ticker == ticker)

    stmt = (
        select(r_expr.label("r_value"))
        .where(*filters)
        .order_by(Trade.end_date.asc())
    )

    rows = (await db.execute(stmt)).all()
    r_values = [float(r.r_value) for r in rows if r.r_value is not None]

    if not r_values:
        return {
            "equity_curve": [],
            "max_drawdown": 0.0,
            "longest_drawdown_trades": 0,
        }

    equity_curve = []
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    current_drawdown_length = 0
    longest_drawdown = 0

    for r in r_values:
        cumulative += r
        equity_curve.append(cumulative)

        if cumulative > peak:
            peak = cumulative
            current_drawdown_length = 0
        else:
            drawdown = peak - cumulative
            max_drawdown = max(max_drawdown, drawdown)
            current_drawdown_length += 1
            longest_drawdown = max(longest_drawdown, current_drawdown_length)

    return {
        "equity_curve": equity_curve,
        "max_drawdown": float(max_drawdown),
        "longest_drawdown_trades": longest_drawdown,
    }

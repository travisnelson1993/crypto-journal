from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# =================================================
# PERFORMANCE ANALYTICS (RESULTS)
# =================================================
@router.get("/performance")
async def performance_summary(db: AsyncSession = Depends(get_db)):
    """
    Outcome-focused performance analytics (Edgewonk / TradeZella style)
    """

    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_multiple = Trade.realized_pnl / func.nullif(risk_usd, 0)

    pnl_pct = Trade.realized_pnl_pct
    lev_pnl_pct = pnl_pct * func.coalesce(Trade.leverage, 1)

    wins = func.sum(case((Trade.realized_pnl > 0, 1), else_=0))
    losses = func.sum(case((Trade.realized_pnl < 0, 1), else_=0))
    breakeven = func.sum(case((Trade.realized_pnl == 0, 1), else_=0))
    trades = func.count()

    stmt = (
        select(
            trades.label("trades"),
            wins.label("wins"),
            losses.label("losses"),
            breakeven.label("breakeven"),
            (wins / func.nullif(wins + losses, 0) * 100).label("win_rate_ex_be"),
            func.sum(pnl_pct).label("gains_pct"),
            func.avg(pnl_pct).label("avg_return_pct"),
            func.sum(lev_pnl_pct).label("lev_gains_pct"),
            func.avg(lev_pnl_pct).label("avg_return_lev_pct"),
            func.sum(r_multiple).label("total_rr"),
            func.avg(r_multiple).label("avg_rr"),
            func.max(r_multiple).label("largest_rr_win"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    def f(x):
        return float(x) if x is not None else 0.0

    return {
        "trades": row.trades or 0,
        "wins": row.wins or 0,
        "losses": row.losses or 0,
        "breakeven": row.breakeven or 0,
        "win_rate_excluding_breakeven_pct": f(row.win_rate_ex_be),
        "gains_pct": f(row.gains_pct) * 100,
        "avg_return_pct": f(row.avg_return_pct) * 100,
        "lev_gains_pct": f(row.lev_gains_pct) * 100,
        "avg_return_lev_pct": f(row.avg_return_lev_pct) * 100,
        "total_rr": f(row.total_rr),
        "avg_rr": f(row.avg_rr),
        "largest_rr_win": f(row.largest_rr_win),
    }


# =================================================
# RISK / DISCIPLINE METRICS (BASIC)
# =================================================
@router.get("/risk-discipline")
async def risk_discipline_summary(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(
            func.count().label("total_closed"),
            func.sum(case((Trade.stop_loss.is_(None), 1), else_=0)).label("missing_stop"),
            func.sum(case((Trade.stop_loss.isnot(None), 1), else_=0)).label("has_stop"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    total = row.total_closed or 0
    has = row.has_stop or 0
    missing = row.missing_stop or 0

    return {
        "total_closed_trades": total,
        "trades_with_stop_loss": has,
        "trades_missing_stop_loss": missing,
        "percent_with_stop_loss": round((has / total * 100) if total else 0.0, 2),
        "percent_missing_stop_loss": round((missing / total * 100) if total else 0.0, 2),
    }


# =================================================
# DISCIPLINE SCORE v1 (R-BASED)
# =================================================
@router.get("/discipline-score")
async def discipline_score_v1(
    db: AsyncSession = Depends(get_db),
    max_r_allowed: float = 1.0,
    max_leverage: float = 10.0,
):
    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_multiple = Trade.realized_pnl / func.nullif(risk_usd, 0)

    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (and_(r_multiple.isnot(None), func.abs(r_multiple) <= max_r_allowed), 1),
        else_=0,
    )

    leverage_within_limit = case(
        (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
        else_=0,
    )

    stmt = (
        select(
            func.count().label("trades_evaluated"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    stop_rate = float(row.stop_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.40
        + risk_rate * 0.30
        + leverage_rate * 0.30
    ) * 100

    return {
        "trades_evaluated": row.trades_evaluated or 0,
        "discipline_score": round(score, 2),
        "rules": {
            "stop_loss_defined_pct": round(stop_rate * 100, 2),
            "risk_within_limit_pct": round(risk_rate * 100, 2),
            "leverage_within_limit_pct": round(leverage_rate * 100, 2),
        },
    }


# =================================================
# DISCIPLINE SCORE v2 (EQUITY-AWARE, ALL TRADES)
# =================================================
@router.get("/discipline-score/v2")
async def discipline_score_v2(
    db: AsyncSession = Depends(get_db),
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
    equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (
            and_(
                Trade.risk_pct_at_entry.isnot(None),
                Trade.risk_pct_at_entry <= max_risk_pct,
            ),
            1,
        ),
        else_=0,
    )

    leverage_within_limit = case(
        (
            func.coalesce(Trade.leverage, 1) <= max_leverage,
            1,
        ),
        else_=0,
    )

    stmt = (
        select(
            func.count().label("trades_evaluated"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(equity_snapshot_present).label("equity_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    stop_rate = float(row.stop_rate or 0)
    equity_rate = float(row.equity_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.30
        + equity_rate * 0.20
        + risk_rate * 0.30
        + leverage_rate * 0.20
    ) * 100

    return {
        "trades_evaluated": row.trades_evaluated or 0,
        "discipline_score": round(score, 2),
        "note": "Includes legacy trades",
    }


# =================================================
# DISCIPLINE SCORE v2 — ELIGIBLE TRADES ONLY
# =================================================
@router.get("/discipline-score/v2/eligible")
async def discipline_score_v2_eligible(
    db: AsyncSession = Depends(get_db),
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
    equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (
            and_(
                Trade.risk_pct_at_entry.isnot(None),
                Trade.risk_pct_at_entry <= max_risk_pct,
            ),
            1,
        ),
        else_=0,
    )

    leverage_within_limit = case(
        (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
        else_=0,
    )

    stmt = (
        select(
            func.count().label("trades_evaluated"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(equity_snapshot_present).label("equity_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(
            Trade.end_date.isnot(None),
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
            Trade.risk_pct_at_entry.isnot(None),
        )
    )

    row = (await db.execute(stmt)).one()
    trades = int(row.trades_evaluated or 0)

    if trades == 0:
        return {
            "trades_evaluated": 0,
            "discipline_score": None,
            "note": "No eligible trades yet",
        }

    stop_rate = float(row.stop_rate or 0)
    equity_rate = float(row.equity_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.30
        + equity_rate * 0.20
        + risk_rate * 0.30
        + leverage_rate * 0.20
    ) * 100

    return {
        "trades_evaluated": trades,
        "discipline_score": round(score, 2),
        "rules": {
            "stop_loss_defined_pct": round(stop_rate * 100, 2),
            "equity_snapshot_present_pct": round(equity_rate * 100, 2),
            "risk_within_limit_pct": round(risk_rate * 100, 2),
            "leverage_within_limit_pct": round(leverage_rate * 100, 2),
        },
    }


# =================================================
# DISCIPLINE SCORE v2 — ROLLING (ELIGIBLE TRADES ONLY)
# =================================================
@router.get("/discipline-score/v2/eligible/rolling")
async def discipline_score_v2_eligible_rolling(
    db: AsyncSession = Depends(get_db),
    n: int = 20,
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
    equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (
            and_(
                Trade.risk_pct_at_entry.isnot(None),
                Trade.risk_pct_at_entry <= max_risk_pct,
            ),
            1,
        ),
        else_=0,
    )

    leverage_within_limit = case(
        (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
        else_=0,
    )

    eligible_trades_subq = (
        select(Trade.id)
        .where(
            Trade.end_date.isnot(None),
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
            Trade.risk_pct_at_entry.isnot(None),
        )
        .order_by(Trade.end_date.desc(), Trade.id.desc())
        .limit(n)
        .subquery()
    )

    stmt = (
        select(
            func.count().label("trades"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(equity_snapshot_present).label("equity_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(Trade.id.in_(select(eligible_trades_subq.c.id)))
    )

    row = (await db.execute(stmt)).one()
    trades = int(row.trades or 0)

    if trades == 0:
        return {
            "window_size": n,
            "trades_evaluated": 0,
            "discipline_score": None,
        }

    stop_rate = float(row.stop_rate or 0)
    equity_rate = float(row.equity_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.30
        + equity_rate * 0.20
        + risk_rate * 0.30
        + leverage_rate * 0.20
    ) * 100

    return {
        "window_size": n,
        "trades_evaluated": trades,
        "discipline_score": round(score, 2),
    }

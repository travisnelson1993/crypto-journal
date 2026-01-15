# app/api/analytics.py
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/performance")
async def performance_summary(db: AsyncSession = Depends(get_db)):
    """
    Professional performance metrics (Edgewonk / TradeZella style)
    """

    # R-multiple expression
    risk_usd = func.abs(Trade.entry_price - Trade.stop_loss) * Trade.original_quantity
    r = Trade.realized_pnl / func.nullif(risk_usd, 0)

    pnl_pct = Trade.realized_pnl_pct
    lev_pnl_pct = pnl_pct * func.nullif(Trade.leverage, 0)

    wins = func.sum(case((Trade.realized_pnl > 0, 1), else_=0))
    losses = func.sum(case((Trade.realized_pnl < 0, 1), else_=0))
    trades = func.count()

    stmt = select(
        trades.label("trades"),
        wins.label("wins"),
        losses.label("losses"),
        (wins / func.nullif((wins + losses), 0) * 100).label("win_rate_pct"),
        (func.sum(pnl_pct) * 100).label("gains_pct"),
        (func.avg(pnl_pct) * 100).label("avg_return_pct"),
        (func.sum(lev_pnl_pct) * 100).label("lev_gains_pct"),
        (func.avg(lev_pnl_pct) * 100).label("avg_return_lev_pct"),
        func.sum(r).label("total_rr"),
        func.avg(r).label("avg_rr"),
        (func.max(pnl_pct) * 100).label("largest_win_pct"),
        (func.max(lev_pnl_pct) * 100).label("largest_lev_pct"),
        func.max(r).label("largest_rr_win"),
    ).where(Trade.end_date.isnot(None))

    row = (await db.execute(stmt)).one()

    def f(x):
        return float(x) if x is not None else 0.0

    return {
        "trades": row.trades,
        "wins": row.wins,
        "losses": row.losses,
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


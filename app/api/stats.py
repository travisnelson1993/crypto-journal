from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.enums import TradeDirection
from app.models.trade import Trade
from app.services.metrics import compute_sheet_metrics

router = APIRouter(prefix="/api/stats", tags=["stats"])


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def _round2(x: float) -> float:
    return round(float(x), 2)


@router.get("/monthly")
async def monthly_stats(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Monthly stats are bucketed by ENTRY_DATE month (trade opened month).

    - trades: counts ALL trades opened that month (even if still open)
    - performance stats: only count CLOSED trades (exit_price is not None)
    - R:R is SIGNED (losers negative) and matches your Google Sheets formulas
    """
    result = await db.execute(
        select(Trade).order_by(Trade.entry_date.asc(), Trade.id.asc())
    )
    trades = result.scalars().all()

    buckets: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        month = t.entry_date.strftime("%Y-%m")
        buckets[month].append(t)

    out: List[Dict[str, Any]] = []

    for month, month_trades in sorted(buckets.items()):
        trades_count = len(month_trades)

        closed = [t for t in month_trades if t.exit_price is not None]

        # Compute per-closed-trade metrics (sheet exact)
        pnl_list: List[float] = []
        lev_pnl_list: List[float] = []
        rr_list: List[float] = []

        wins = losses = breakeven = 0

        for t in closed:
            status_, pnl_, lev_pnl_, rr_ = compute_sheet_metrics(
                direction=TradeDirection(t.direction),
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                stop_loss=t.stop_loss,
                leverage=t.leverage,
            )

            if pnl_ is not None:
                pnl_list.append(pnl_)
                lev_pnl_list.append(lev_pnl_ if lev_pnl_ is not None else 0.0)

                if pnl_ > 0:
                    wins += 1
                elif pnl_ < 0:
                    losses += 1
                else:
                    breakeven += 1

            if rr_ is not None:
                rr_list.append(rr_)

        closed_trades = len(closed)

        # Sheet formulas:
        # Win Rate % = wins / (wins + losses)
        denom = wins + losses
        win_rate_pct = _round2((wins / denom) * 100.0) if denom > 0 else 0.0

        # Gains % = SUM(K)
        gains_pct = _round2(sum(pnl_list)) if pnl_list else 0.0

        # Avg. Return % = AVERAGE(K)
        avg_return_pct = _round2(sum(pnl_list) / len(pnl_list)) if pnl_list else 0.0

        # Lev. Gains % = SUM(L)
        lev_gains_pct = _round2(sum(lev_pnl_list)) if lev_pnl_list else 0.0

        # Avg. Return (Lev.) = AVERAGE(L)
        avg_return_lev_pct = (
            _round2(sum(lev_pnl_list) / len(lev_pnl_list)) if lev_pnl_list else 0.0
        )

        # Total R:R = SUM(M)
        total_rr = _round2(sum(rr_list)) if rr_list else 0.0

        # Avg. R:R = ROUND(AVERAGE(M),2)
        avg_rr = _round2(sum(rr_list) / len(rr_list)) if rr_list else 0.0

        # Largest Win % = MAX(K)
        largest_win_pct = max(pnl_list) if pnl_list else 0.0

        # Largest Lev. % = MAX(L)
        largest_lev_win_pct = max(lev_pnl_list) if lev_pnl_list else 0.0

        # Largest R:R Win = MAX(M)
        largest_rr_win = max(rr_list) if rr_list else 0.0

        out.append(
            {
                "month": month,
                "trades": trades_count,
                "closed_trades": closed_trades,
                "wins": wins,
                "losses": losses,
                "breakeven": breakeven,
                "win_rate_pct": win_rate_pct,
                "gains_pct": gains_pct,
                "avg_return_pct": avg_return_pct,
                "lev_gains_pct": lev_gains_pct,
                "avg_return_lev_pct": avg_return_lev_pct,
                "total_rr": total_rr,
                "avg_rr": avg_rr,
                "largest_win_pct": largest_win_pct,
                "largest_lev_win_pct": largest_lev_win_pct,
                "largest_rr_win": largest_rr_win,
            }
        )

    return out

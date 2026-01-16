from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade


async def compute_daily_max_loss(
    db: AsyncSession,
    *,
    max_daily_loss_usd: float = 100.0,
    eligible_only: bool = False,
) -> dict:
    today = datetime.utcnow().date()

    stmt = (
        select(
            Trade.id,
            Trade.end_date,
            Trade.realized_pnl,
        )
        .where(
            Trade.end_date.isnot(None),
            func.date(Trade.end_date) == today,
        )
        .order_by(Trade.end_date.asc(), Trade.id.asc())
    )

    if eligible_only:
        stmt = stmt.where(
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
        )

    rows = (await db.execute(stmt)).all()

    trades = []
    daily_pnl = 0.0

    for trade_id, end_date, pnl in rows:
        if pnl is None:
            continue

        pnl_f = float(pnl)
        daily_pnl += pnl_f

        trades.append({
            "trade_id": trade_id,
            "end_date": end_date.isoformat(),
            "realized_pnl": pnl_f,
        })

    trading_halted = daily_pnl <= -abs(max_daily_loss_usd)

    return {
        "date": today.isoformat(),
        "daily_pnl": round(daily_pnl, 2),
        "max_daily_loss_usd": round(max_daily_loss_usd, 2),
        "trading_halted": trading_halted,
        "halt_reason": (
            "Daily loss limit exceeded" if trading_halted else None
        ),
        "trades": trades,
    }

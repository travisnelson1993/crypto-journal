from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade


async def compute_loss_streaks(
    db: AsyncSession,
    *,
    eligible_only: bool = False,
    max_losses: int = 3,
) -> dict:
    stmt = (
        select(
            Trade.id,
            Trade.end_date,
            Trade.realized_pnl,
        )
        .where(Trade.end_date.isnot(None))
        .order_by(Trade.end_date.asc(), Trade.id.asc())
    )

    if eligible_only:
        stmt = stmt.where(
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
        )

    rows = (await db.execute(stmt)).all()

    current_streak = 0
    max_streak_seen = 0
    recent_losses = []

    for trade_id, end_date, pnl in rows:
        if pnl is None or pnl >= 0:
            current_streak = 0
            recent_losses.clear()
            continue

        # loss
        current_streak += 1
        max_streak_seen = max(max_streak_seen, current_streak)

        recent_losses.append({
            "trade_id": trade_id,
            "end_date": end_date.isoformat(),
            "realized_pnl": float(pnl),
        })

    trading_halted = current_streak >= max_losses

    return {
        "current_loss_streak": current_streak,
        "max_loss_streak": max_streak_seen,
        "trading_halted": trading_halted,
        "halt_rule": f"max {max_losses} consecutive losses",
        "recent_losses": recent_losses[-max_losses:],
    }

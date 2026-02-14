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
    """
    CATEGORY 4 — Risk Governance (Advisory Only)

    Computes daily realized PnL and emits an advisory warning if the
    configured daily loss threshold is exceeded.

    ❌ No enforcement
    ❌ No trade blocking
    ❌ No permission flags
    """

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

    daily_loss_exceeded = daily_pnl <= -abs(max_daily_loss_usd)

    return {
        "date": today.isoformat(),
        "daily_pnl": round(daily_pnl, 2),
        "max_daily_loss_usd": round(max_daily_loss_usd, 2),
        "daily_loss_exceeded": daily_loss_exceeded,
        "warning": (
            {
                "type": "DAILY_MAX_LOSS_EXCEEDED",
                "severity": "HIGH",
                "message": "Daily loss exceeded configured maximum.",
                "confidence": 0.9,
            }
            if daily_loss_exceeded
            else None
        ),
        "trades": trades,
    }

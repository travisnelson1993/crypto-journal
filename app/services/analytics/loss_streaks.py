from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade


def _loss_streak_warning(streak: int) -> dict | None:
    """
    Awareness-only warning builder.
    No enforcement, no halting.
    """
    if streak >= 5:
        return {
            "type": "LOSS_STREAK",
            "severity": "HIGH",
            "message": f"{streak} consecutive losses detected. Strongly consider stopping for the session.",
            "confidence": 0.9,
        }
    if streak >= 3:
        return {
            "type": "LOSS_STREAK",
            "severity": "MEDIUM",
            "message": f"{streak} consecutive losses detected. Risk of tilt is elevated.",
            "confidence": 0.8,
        }
    if streak >= 2:
        return {
            "type": "LOSS_STREAK",
            "severity": "LOW",
            "message": f"{streak} consecutive losses detected. Maintain discipline and reduce size.",
            "confidence": 0.65,
        }
    return None


async def compute_loss_streaks(
    db: AsyncSession,
    *,
    eligible_only: bool = False,
    lookback_trades: int = 200,
) -> dict:
    """
    Trader-grade loss streak analytics (ENGINE).
    Awareness only. No enforcement.
    """

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

    if lookback_trades and len(rows) > lookback_trades:
        rows = rows[-lookback_trades:]

    current_streak = 0
    max_streak_seen = 0
    points = []

    for trade_id, end_date, pnl in rows:
        pnl_val = float(pnl or 0)

        if pnl_val < 0:
            current_streak += 1
        else:
            current_streak = 0

        max_streak_seen = max(max_streak_seen, current_streak)

        points.append(
            {
                "trade_id": trade_id,
                "end_date": end_date.isoformat(),
                "realized_pnl": pnl_val,
                "outcome": (
                    "LOSS"
                    if pnl_val < 0
                    else "PROFIT"
                    if pnl_val > 0
                    else "BREAKEVEN"
                ),
                "streak_after": current_streak,
            }
        )

    warnings = []
    w = _loss_streak_warning(current_streak)
    if w:
        warnings.append(w)

    return {
        "current_loss_streak": current_streak,
        "max_loss_streak_seen": max_streak_seen,
        "warnings": warnings,
        "points": points,
    }


# ✅ PUBLIC CONTRACT (what tests + API import)
async def loss_streak_summary(
    db: AsyncSession,
    *,
    eligible_only: bool = False,
    lookback_trades: int = 200,
) -> dict:
    """
    Stable public wrapper for loss streak analytics.
    """
    return await compute_loss_streaks(
        db,
        eligible_only=eligible_only,
        lookback_trades=lookback_trades,
    )

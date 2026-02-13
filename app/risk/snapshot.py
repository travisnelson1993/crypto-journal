from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.loss_streaks import compute_loss_streaks
from app.services.analytics.daily_max_loss import compute_daily_max_loss


async def build_risk_warnings(
    db: AsyncSession,
    *,
    proposed_risk_pct: float | None = None,
) -> dict | None:
    """
    SOFT risk warnings captured at trade entry.
    Never blocks execution.
    """
    warnings = {}

    # ---- Loss streak ----
    try:
        streak = await compute_loss_streaks(db, eligible_only=True)
        warnings["loss_streak"] = streak["current_loss_streak"]
        warnings["loss_streak_halt"] = streak["trading_halted"]
    except Exception:
        warnings["loss_streak"] = "unavailable"

    # ---- Daily max loss ----
    try:
        daily = await compute_daily_max_loss(db, eligible_only=True)
        warnings["daily_pnl"] = daily["daily_pnl"]
        warnings["daily_loss_halt"] = daily["trading_halted"]
    except Exception:
        warnings["daily_loss"] = "unavailable"

    return warnings or None

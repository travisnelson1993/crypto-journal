from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade

# -------------------------------------------------
# OPTIONAL analytics dependencies (future-ready)
# -------------------------------------------------
try:
    from app.services.analytics.loss_streaks import get_loss_streak
except ImportError:
    get_loss_streak = None  # not implemented yet

try:
    from app.services.analytics.equity_regime import get_equity_regime
except ImportError:
    get_equity_regime = None  # not implemented yet


async def position_sizing(db: AsyncSession) -> Dict[str, Any]:
    """
    Advisory-only position sizing engine.

    - NEVER blocks trades
    - Returns guidance only
    - Safe to call even if analytics are incomplete
    """

    # -------------------------------------------------
    # Defaults (safe baseline)
    # -------------------------------------------------
    result: Dict[str, Any] = {
        "trading_allowed": True,
        "allowed_risk_pct": 0.02,
        "regime": "normal",
        "notes": None,
    }

    # -------------------------------------------------
    # Loss streak analysis (if implemented)
    # -------------------------------------------------
    if get_loss_streak:
        loss_streak = await get_loss_streak(db)

        if loss_streak >= 3:
            result.update(
                {
                    "trading_allowed": False,
                    "allowed_risk_pct": 0.01,
                    "regime": "loss_streak",
                    "notes": f"{loss_streak} consecutive losing trades",
                }
            )
            return result

    # -------------------------------------------------
    # Equity regime analysis (if implemented)
    # -------------------------------------------------
    if get_equity_regime:
        equity_regime = await get_equity_regime(db)

        if equity_regime == "drawdown":
            result.update(
                {
                    "trading_allowed": False,
                    "allowed_risk_pct": 0.01,
                    "regime": "drawdown",
                    "notes": "Account equity is in drawdown",
                }
            )
            return result

    # -------------------------------------------------
    # Healthy state
    # -------------------------------------------------
    result["regime"] = "healthy"
    result["allowed_risk_pct"] = 0.02

    return result

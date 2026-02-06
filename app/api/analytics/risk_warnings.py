from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade
from app.services.analytics.daily_max_loss import compute_daily_max_loss

router = APIRouter(
    prefix="/api/analytics/risk-warnings",
    tags=["analytics"],
)


@router.get("/summary")
async def risk_warning_summary(db: AsyncSession = Depends(get_db)):
    """
    High-level summary of risk warnings across all trades.
    Read-only. Advisory only.

    This endpoint aggregates advisory risk signals.
    No enforcement logic exists here.
    """

    result = await db.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.sum(
                case(
                    (func.jsonb_array_length(Trade.risk_warnings) > 0, 1),
                    else_=0,
                )
            ).label("trades_with_warnings"),
        )
    )

    row = result.one()

    total = row.total_trades or 0
    warned = row.trades_with_warnings or 0

    # -------------------------------------------------
    # Advisory-only aggregated warnings
    # -------------------------------------------------
    warnings = []

    daily_loss_result = await compute_daily_max_loss(db)
    if daily_loss_result.get("warning"):
        warnings.append(daily_loss_result["warning"])

    return {
        "total_trades": total,
        "trades_with_warnings": warned,
        "warning_rate": round((warned / total), 4) if total else 0.0,
        "warnings": warnings,
        "enforcement": False,
    }

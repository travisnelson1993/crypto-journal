from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

router = APIRouter(
    prefix="/api/analytics/risk-warnings",
    tags=["analytics"],
)


@router.get("/summary")
async def risk_warning_summary(db: AsyncSession = Depends(get_db)):
    """
    High-level summary of risk warnings across all trades.
    Read-only. Advisory only.
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

    return {
        "total_trades": total,
        "trades_with_warnings": warned,
        "warning_rate": round((warned / total), 4) if total else 0.0,
        "enforcement": False,
    }

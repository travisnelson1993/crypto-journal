# app/api/positions.py

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.db.database import get_db
from app.models.trade import Trade
from app.schemas.positions import PositionState

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("", response_model=list[PositionState])
async def get_positions(db: AsyncSession = Depends(get_db)):
    """
    Canonical open position state.
    One row per ticker + side.
    """
    stmt = (
        select(
            Trade.ticker.label("ticker"),
            Trade.direction.label("side"),
            func.sum(Trade.quantity).label("net_quantity"),
            (
                func.sum(Trade.entry_price * Trade.quantity)
                / func.nullif(func.sum(Trade.quantity), 0)
            ).label("avg_entry_price"),
            func.count().label("open_trades"),
            func.min(Trade.entry_date).label("first_entry_date"),
            func.max(Trade.entry_date).label("last_entry_date"),
            func.max(Trade.leverage).label("leverage_max"),
        )
        .where(
            Trade.end_date.is_(None),
            Trade.quantity > 0,
        )
        .group_by(Trade.ticker, Trade.direction)
        .order_by(func.min(Trade.entry_date))
    )

    result = await db.execute(stmt)

    positions: list[PositionState] = []

    for r in result.all():
        net_qty = Decimal(r.net_quantity)
        avg_price = Decimal(r.avg_entry_price)

        notional = abs(net_qty * avg_price)
        exposure = notional

        leverage_weighted = (
            Decimal(r.leverage_max) if r.leverage_max else None
        )

        margin_estimate = (
            exposure / leverage_weighted
            if leverage_weighted and leverage_weighted > 0
            else None
        )

        positions.append(
            PositionState(
                ticker=r.ticker,
                side=r.side,
                net_quantity=net_qty,
                avg_entry_price=avg_price,
                notional_usd=notional,
                exposure_usd=exposure,
                open_trades=r.open_trades,
                first_entry_date=r.first_entry_date,
                last_entry_date=r.last_entry_date,
                leverage_max=r.leverage_max,
                leverage_weighted=leverage_weighted,
                margin_estimate_usd=margin_estimate,
                unrealized_pnl_usd=None,
                realized_pnl_usd=None,
            )
        )

    return positions

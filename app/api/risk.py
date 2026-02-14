from fastapi import APIRouter, HTTPException
from decimal import Decimal

from app.schemas.position_sizing import (
    PositionSizeRequest,
    PositionSizeResponse,
)
from app.services.position_sizing import calculate_position_size

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.post("/position-size", response_model=PositionSizeResponse)
def position_size_calculator(payload: PositionSizeRequest):
    # Basic validation guardrails
    if payload.entry_price == payload.stop_loss:
        raise HTTPException(
            status_code=400,
            detail="entry_price and stop_loss cannot be equal",
        )

    sizing = calculate_position_size(
        equity=payload.equity,
        risk_pct=payload.risk_pct,
        entry_price=payload.entry_price,
        stop_loss=payload.stop_loss,
    )

    rr = None
    if payload.target_price is not None:
        risk = abs(payload.entry_price - payload.stop_loss)
        reward = abs(payload.target_price - payload.entry_price)
        if risk > 0:
            rr = Decimal(reward) / Decimal(risk)

    return PositionSizeResponse(
        quantity=sizing["quantity"],
        notional=sizing["notional"],
        risk_amount=sizing["risk_amount"],
        price_distance=sizing["price_distance"],
        rr=rr,
    )

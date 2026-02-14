from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal


class PositionSizeRequest(BaseModel):
    equity: Decimal = Field(..., gt=0)
    risk_pct: Decimal = Field(..., gt=0, lt=1)
    entry_price: Decimal = Field(..., gt=0)
    stop_loss: Decimal = Field(..., gt=0)
    target_price: Optional[Decimal] = Field(None, gt=0)


class PositionSizeResponse(BaseModel):
    quantity: Decimal
    notional: Decimal
    risk_amount: Decimal
    price_distance: Decimal
    rr: Optional[Decimal] = None

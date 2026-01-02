from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import TradeDirection


class TradeCreate(BaseModel):
    ticker: str
    direction: TradeDirection  # SPOT / LONG / SHORT
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    leverage: float = 1
    entry_date: datetime
    end_date: Optional[datetime] = None
    entry_summary: Optional[str] = None


class TradeOut(TradeCreate):
    id: int

    # Computed fields (Google Sheets-style)
    status: Optional[str] = None  # PROFIT / BREAKEVEN / LOSS / OPEN
    pnl_pct: Optional[float] = None  # K
    lev_pnl_pct: Optional[float] = None  # L
    rr: Optional[float] = None  # M

    model_config = ConfigDict(from_attributes=True)

from datetime import datetime
from pydantic import BaseModel


class PositionState(BaseModel):
    ticker: str
    direction: str

    net_quantity: float
    avg_entry_price: float

    notional_value: float
    exposure_usd: float

    open_trades: int

    first_entry_date: datetime
    last_entry_date: datetime | None = None

    leverage_weighted: float | None = None
    margin_estimate: float | None = None

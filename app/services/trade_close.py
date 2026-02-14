from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.models.trade import Trade


def _as_decimal(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def close_trade(
    trade: Trade,
    exit_price: Decimal,
    closed_at: Optional[datetime] = None,
    fee: Optional[Decimal] = None,
) -> Trade:
    """
    Close a trade and compute realized PnL immediately (professional-grade rule).
    """
    if trade.end_date is not None:
        raise ValueError("Trade is already closed.")

    if closed_at is None:
        closed_at = datetime.now(timezone.utc)

    qty = _as_decimal(trade.original_quantity)
    entry = _as_decimal(trade.entry_price)
    exit_ = _as_decimal(exit_price)

    if trade.direction == "long":
        pnl = (exit_ - entry) * qty
    elif trade.direction == "short":
        pnl = (entry - exit_) * qty
    else:
        raise ValueError(f"Invalid direction: {trade.direction}")

    fee_to_use = _as_decimal(fee) if fee is not None else _as_decimal(trade.fee or Decimal("0"))
    pnl -= fee_to_use

    notional = entry * qty
    pnl_pct = (pnl / notional) if notional != 0 else Decimal("0")

    trade.exit_price = exit_
    trade.end_date = closed_at
    trade.realized_pnl = pnl
    trade.realized_pnl_pct = pnl_pct

    return trade

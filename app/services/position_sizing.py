from typing import Dict


class PositionSizingError(ValueError):
    """Raised when position sizing inputs are invalid."""


def calculate_position_size(
    *,
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
) -> Dict[str, float]:
    """
    Calculate position size using fixed-risk futures-style sizing.

    All values are USDT-based.

    Advisory only:
    - Does not mutate trades
    - Does not enforce limits
    """

    # --- Validation ---
    if equity <= 0:
        raise PositionSizingError("Equity must be greater than zero.")

    if risk_pct <= 0 or risk_pct > 1:
        raise PositionSizingError("risk_pct must be between 0 and 1 (e.g. 0.01 for 1%).")

    if entry_price <= 0:
        raise PositionSizingError("Entry price must be greater than zero.")

    if stop_loss <= 0:
        raise PositionSizingError("Stop-loss price must be greater than zero.")

    price_distance = abs(entry_price - stop_loss)
    if price_distance == 0:
        raise PositionSizingError("Entry price and stop-loss cannot be the same.")

    # --- Core math ---
    risk_amount = equity * risk_pct
    quantity = risk_amount / price_distance
    notional = quantity * entry_price

    return {
        "quantity": quantity,
        "notional": notional,
        "risk_amount": risk_amount,
        "price_distance": price_distance,
    }

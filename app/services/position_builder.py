# app/services/position_builder.py

from dataclasses import dataclass
from typing import Iterable, List
from decimal import Decimal


@dataclass
class PositionSnapshot:
    account_id: int
    symbol: str
    side: str  # "LONG" or "SHORT"
    opened_qty: Decimal
    closed_qty: Decimal
    remaining_qty: Decimal
    avg_entry_price: Decimal | None
    realized_pnl: Decimal
    opened_at: object
    closed_at: object | None


def build_position_snapshot(trades: Iterable) -> PositionSnapshot:
    """
    Build a single position snapshot from a list of trades
    belonging to the same (account, symbol, side).

    Assumptions:
    - trades are executions (opens, DCA adds, partial closes)
    - BUY increases size for LONG, SELL decreases (inverse for SHORT)
    - prices and quantities are positive numbers
    """

    trades = sorted(trades, key=lambda t: t.entry_date)

    if not trades:
        raise ValueError("No trades provided")

    account_id = trades[0].account_id
    symbol = trades[0].ticker
    side = trades[0].direction

    opened_qty = Decimal("0")
    closed_qty = Decimal("0")
    cost_basis = Decimal("0")
    realized_pnl = Decimal("0")

    opened_at = trades[0].entry_date
    closed_at = None

    for t in trades:
        qty = Decimal(str(t.quantity))
        price = Decimal(str(t.entry_price))

        if t.is_open:  # OPEN / DCA ADD
            opened_qty += qty
            cost_basis += qty * price

        else:  # CLOSE / PARTIAL CLOSE
            remaining_before = opened_qty - closed_qty
            close_qty = min(qty, remaining_before)

            if close_qty <= 0:
                continue

            avg_entry = cost_basis / opened_qty if opened_qty > 0 else Decimal("0")

            pnl = close_qty * (Decimal(str(t.exit_price)) - avg_entry)
            realized_pnl += pnl

            closed_qty += close_qty

            if closed_qty == opened_qty:
                closed_at = t.end_date

    remaining_qty = opened_qty - closed_qty
    avg_entry_price = (
        (cost_basis / opened_qty) if opened_qty > 0 else None
    )

    return PositionSnapshot(
        account_id=account_id,
        symbol=symbol,
        side=side,
        opened_qty=opened_qty,
        closed_qty=closed_qty,
        remaining_qty=remaining_qty,
        avg_entry_price=avg_entry_price,
        realized_pnl=realized_pnl,
        opened_at=opened_at,
        closed_at=closed_at,
    )

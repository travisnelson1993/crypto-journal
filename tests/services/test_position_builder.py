from decimal import Decimal
from datetime import datetime

from app.services.position_builder import build_position_snapshot


class FakeTrade:
    def __init__(
        self,
        account_id,
        ticker,
        direction,
        quantity,
        entry_price,
        is_open,
        exit_price=None,
        entry_date=None,
        end_date=None,
    ):
        self.account_id = account_id
        self.ticker = ticker
        self.direction = direction
        self.quantity = quantity
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.is_open = is_open
        self.entry_date = entry_date or datetime.utcnow()
        self.end_date = end_date


def test_open_then_partial_close():
    trades = [
        FakeTrade(
            account_id=1,
            ticker="BTCUSDT",
            direction="LONG",
            quantity=0.10,
            entry_price=100_000,
            is_open=True,
        ),
        FakeTrade(
            account_id=1,
            ticker="BTCUSDT",
            direction="LONG",
            quantity=0.05,
            entry_price=100_000,
            exit_price=102_000,
            is_open=False,
        ),
    ]

    pos = build_position_snapshot(trades)

    assert pos.opened_qty == Decimal("0.10")
    assert pos.closed_qty == Decimal("0.05")
    assert pos.remaining_qty == Decimal("0.05")
    assert pos.realized_pnl == Decimal("100.0")  # 0.05 * (102k - 100k)
    assert pos.unrealized_pnl is None


def test_multiple_dca_and_closes():
    trades = [
        FakeTrade(1, "BTCUSDT", "LONG", 0.10, 100_000, True),
        FakeTrade(1, "BTCUSDT", "LONG", 0.10, 101_000, True),
        FakeTrade(1, "BTCUSDT", "LONG", 0.15, 100_000, False, exit_price=102_000),
    ]

    pos = build_position_snapshot(trades)

    assert pos.opened_qty == Decimal("0.20")
    assert pos.closed_qty == Decimal("0.15")
    assert pos.remaining_qty == Decimal("0.05")
    assert pos.realized_pnl > 0
    assert pos.unrealized_pnl is None


def test_unrealized_pnl_long_position():
    trades = [
        FakeTrade(1, "BTCUSDT", "LONG", 0.10, 100_000, True),
        FakeTrade(1, "BTCUSDT", "LONG", 0.05, 100_000, False, exit_price=101_000),
    ]

    pos = build_position_snapshot(trades, current_price=102_000)

    # remaining = 0.05
    # avg entry = 100_000
    # unrealized = 0.05 * (102k - 100k) = 100
    assert pos.remaining_qty == Decimal("0.05")
    assert pos.unrealized_pnl == Decimal("100.0")


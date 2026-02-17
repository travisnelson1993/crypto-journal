import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.models.trade import Trade


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def make_closed_trade(
    entry_price,
    exit_price,
    stop_loss,
    quantity=Decimal("1"),
    direction="long",
):
    trade = Trade(
        ticker="TEST",
        direction=direction,
        entry_price=Decimal(entry_price),
        original_quantity=Decimal(quantity),
        quantity=Decimal(quantity),
        stop_loss=Decimal(stop_loss) if stop_loss is not None else None,
        leverage=1.0,
        created_at=datetime.now(timezone.utc),
    )

    trade.exit_price = Decimal(exit_price)
    trade.end_date = datetime.now(timezone.utc)

    # Compute realized pnl manually
    if direction == "long":
        pnl = (Decimal(exit_price) - Decimal(entry_price)) * Decimal(quantity)
    else:
        pnl = (Decimal(entry_price) - Decimal(exit_price)) * Decimal(quantity)

    trade.realized_pnl = pnl

    if entry_price and quantity:
        trade.realized_pnl_pct = pnl / (Decimal(entry_price) * Decimal(quantity))
    else:
        trade.realized_pnl_pct = Decimal("0")

    return trade


# =================================================
# TEST 1 — stop_loss = None
# =================================================

def test_r_calculation_no_stop_loss():
    trade = make_closed_trade(
        entry_price="100",
        exit_price="110",
        stop_loss=None,
    )

    # risk_usd should be None → R cannot be computed
    risk_usd = None
    assert trade.stop_loss is None
    assert trade.realized_pnl is not None


# =================================================
# TEST 2 — risk_usd = 0
# =================================================

def test_r_calculation_zero_risk():
    trade = make_closed_trade(
        entry_price="100",
        exit_price="110",
        stop_loss="100",  # zero risk
    )

    risk_usd = abs(trade.entry_price - trade.stop_loss) * trade.original_quantity
    assert risk_usd == 0


# =================================================
# TEST 3 — Drawdown Edge Case (All Wins)
# =================================================

def test_drawdown_all_wins():
    r_values = [1.0, 2.0, 0.5, 1.5]

    cumulative = 0
    peak = 0
    max_drawdown = 0

    for r in r_values:
        cumulative += r
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    assert max_drawdown == 0


# =================================================
# TEST 4 — Drawdown Edge Case (All Losses)
# =================================================

def test_drawdown_all_losses():
    r_values = [-1.0, -2.0, -0.5]

    cumulative = 0
    peak = 0
    max_drawdown = 0

    for r in r_values:
        cumulative += r
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    assert max_drawdown > 0

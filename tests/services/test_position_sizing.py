import pytest

from app.services.position_sizing import (
    calculate_position_size,
    PositionSizingError,
)


def test_position_sizing_normal_case():
    result = calculate_position_size(
        equity=1000.0,
        risk_pct=0.01,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert result["risk_amount"] == pytest.approx(10.0)
    assert result["price_distance"] == pytest.approx(5.0)
    assert result["quantity"] == pytest.approx(2.0)
    assert result["notional"] == pytest.approx(200.0)


def test_position_sizing_stop_above_entry():
    result = calculate_position_size(
        equity=1000.0,
        risk_pct=0.02,
        entry_price=100.0,
        stop_loss=105.0,
    )

    assert result["risk_amount"] == pytest.approx(20.0)
    assert result["price_distance"] == pytest.approx(5.0)
    assert result["quantity"] == pytest.approx(4.0)


def test_invalid_equity():
    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=0,
            risk_pct=0.01,
            entry_price=100,
            stop_loss=95,
        )


def test_invalid_risk_pct():
    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=1000,
            risk_pct=0,
            entry_price=100,
            stop_loss=95,
        )

    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=1000,
            risk_pct=1.5,
            entry_price=100,
            stop_loss=95,
        )


def test_invalid_prices():
    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=1000,
            risk_pct=0.01,
            entry_price=0,
            stop_loss=95,
        )

    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=1000,
            risk_pct=0.01,
            entry_price=100,
            stop_loss=100,
        )

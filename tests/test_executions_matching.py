from decimal import Decimal
from datetime import datetime, timezone
from app.models.executions import Execution
from app.services.matcher import fifo_match_close

def test_fifo_partial_close(session):
    open1 = Execution(
        source="test",
        ticker="BTCUSDT",
        side="OPEN",
        direction="LONG",
        price=Decimal("100"),
        quantity=Decimal("2"),
        remaining_qty=Decimal("2"),
        timestamp=datetime.now(timezone.utc),
    )

    close1 = Execution(
        source="test",
        ticker="BTCUSDT",
        side="CLOSE",
        direction="LONG",
        price=Decimal("110"),
        quantity=Decimal("1"),
        remaining_qty=Decimal("1"),
        timestamp=datetime.now(timezone.utc),
    )

    session.add_all([open1, close1])
    session.commit()

    fifo_match_close(session, close1)
    session.commit()

    assert open1.remaining_qty == Decimal("1")
    assert close1.remaining_qty == Decimal("0")

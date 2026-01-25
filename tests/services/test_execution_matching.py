import pytest
from decimal import Decimal
from datetime import datetime

from app.models.executions import Execution, ExecutionMatch
from app.services.execution_matching import match_close_execution


@pytest.mark.asyncio
async def test_fifo_full_match(async_session):
    open_exec = Execution(
        source="test",
        ticker="BTCUSDT",
        side="OPEN",
        direction="LONG",
        price=Decimal("40000"),
        quantity=Decimal("1"),
        remaining_qty=Decimal("1"),
        timestamp=datetime(2024, 1, 1, 10, 0, 0),
    )

    close_exec = Execution(
        source="test",
        ticker="BTCUSDT",
        side="CLOSE",
        direction="LONG",
        price=Decimal("41000"),
        quantity=Decimal("1"),
        remaining_qty=Decimal("1"),
        timestamp=datetime(2024, 1, 1, 11, 0, 0),
    )

    async_session.add_all([open_exec, close_exec])
    await async_session.commit()

    await match_close_execution(async_session, close_exec)
    await async_session.commit()

    await async_session.refresh(open_exec)
    await async_session.refresh(close_exec)

    assert open_exec.remaining_qty == 0
    assert close_exec.remaining_qty == 0

    result = await async_session.execute(
        ExecutionMatch.__table__.select()
    )
    matches = result.fetchall()

    assert len(matches) == 1
    assert matches[0].matched_quantity == Decimal("1")


from datetime import datetime

@pytest.mark.asyncio
async def test_fifo_partial_close(async_session):
    open_exec = Execution(
        source="test",
        ticker="BTCUSDT",
        side="OPEN",
        direction="LONG",
        price=Decimal("40000"),
        quantity=Decimal("2"),
        remaining_qty=Decimal("2"),
        timestamp=datetime(2024, 1, 1, 10, 0, 0),
    )

    close_exec = Execution(
        source="test",
        ticker="BTCUSDT",
        side="CLOSE",
        direction="LONG",
        price=Decimal("41000"),
        quantity=Decimal("0.5"),
        remaining_qty=Decimal("0.5"),
        timestamp=datetime(2024, 1, 1, 11, 0, 0),
    )

    async_session.add_all([open_exec, close_exec])
    await async_session.commit()

    await match_close_execution(async_session, close_exec)
    await async_session.commit()

    await async_session.refresh(open_exec)
    await async_session.refresh(close_exec)

    assert open_exec.remaining_qty == Decimal("1.5")
    assert close_exec.remaining_qty == Decimal("0")

import pytest
from decimal import Decimal
from datetime import datetime

from app.models.executions import Execution, ExecutionMatch
from app.services.execution_matching import match_close_execution


@pytest.mark.asyncio
async def test_fifo_multiple_opens(async_session):
    open1 = Execution(
        source="test",
        ticker="BTCUSDT",
        side="OPEN",
        direction="LONG",
        price=Decimal("40000"),
        quantity=Decimal("1"),
        remaining_qty=Decimal("1"),
        timestamp=datetime(2024, 1, 1, 9, 0, 0),
    )

    open2 = Execution(
        source="test",
        ticker="BTCUSDT",
        side="OPEN",
        direction="LONG",
        price=Decimal("40500"),
        quantity=Decimal("1"),
        remaining_qty=Decimal("1"),
        timestamp=datetime(2024, 1, 1, 10, 0, 0),
    )

    close_exec = Execution(
        source="test",
        ticker="BTCUSDT",
        side="CLOSE",
        direction="LONG",
        price=Decimal("41000"),
        quantity=Decimal("1.5"),
        remaining_qty=Decimal("1.5"),
        timestamp=datetime(2024, 1, 1, 11, 0, 0),
    )

    async_session.add_all([open1, open2, close_exec])
    await async_session.commit()

    # ---- FIFO match
    await match_close_execution(async_session, close_exec)
    await async_session.commit()

    # ---- Refresh
    await async_session.refresh(open1)
    await async_session.refresh(open2)
    await async_session.refresh(close_exec)

    # ---- Assertions
    assert open1.remaining_qty == Decimal("0")
    assert open2.remaining_qty == Decimal("0.5")
    assert close_exec.remaining_qty == Decimal("0")

    result = await async_session.execute(
        ExecutionMatch.__table__.select()
    )
    matches = result.fetchall()

    assert len(matches) == 2
    assert matches[0].matched_quantity == Decimal("1")
    assert matches[1].matched_quantity == Decimal("0.5")


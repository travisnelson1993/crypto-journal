import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models.executions import Execution, ExecutionMatch
from app.services.execution_matching import match_close_execution


@pytest.mark.asyncio
async def test_readonly_position_aggregation_icp(async_session):
    ticker = "ICPUSDT"
    direction = "LONG"

    # --- Load executions
    result = await async_session.execute(
        select(Execution)
        .where(
            Execution.ticker == ticker,
            Execution.direction == direction,
        )
        .order_by(Execution.timestamp.asc(), Execution.id.asc())
    )
    executions = result.scalars().all()

    assert executions, "No executions found for test symbol"

    # --- Match all CLOSE executions
    for exec_ in executions:
        if exec_.side == "CLOSE":
            await match_close_execution(async_session, exec_)

    await async_session.commit()

    # --- Reload opens
    opens = [
        e for e in executions
        if e.side == "OPEN"
    ]

    # --- Load matches
    matches = (
        await async_session.execute(
            select(ExecutionMatch)
            .join(Execution, ExecutionMatch.open_execution_id == Execution.id)
            .where(Execution.ticker == ticker)
        )
    ).scalars().all()

    total_open_remaining = sum(
        (e.remaining_qty for e in opens),
        Decimal("0")
    )

    total_matched = sum(
        (m.matched_quantity for m in matches),
        Decimal("0")
    )

    # --- Core invariants
    assert total_open_remaining >= 0
    assert total_matched >= 0

    # Sanity: no over-closing
    total_open_qty = sum((e.quantity for e in opens), Decimal("0"))
    assert total_matched <= total_open_qty

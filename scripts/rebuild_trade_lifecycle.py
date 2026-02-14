import asyncio
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_sessionmaker
from app.models.trade import Trade
from app.models.executions import Execution, ExecutionMatch
from app.models.trade_lifecycle_event import TradeLifecycleEvent


async def rebuild_trade_lifecycle(session: AsyncSession) -> int:
    # 0️⃣ Clear derived table
    await session.execute(delete(TradeLifecycleEvent))
    await session.flush()

    # 1️⃣ Load all executions
    executions: Dict[int, Execution] = {
        e.id: e
        for e in (
            await session.execute(select(Execution))
        ).scalars().all()
    }

    # 2️⃣ Load execution matches ordered by time
    matches: List[ExecutionMatch] = (
        await session.execute(
            select(ExecutionMatch).order_by(ExecutionMatch.created_at)
        )
    ).scalars().all()

    # 3️⃣ Group matches by trade (open_execution_id == trade.id)
    matches_by_trade: Dict[int, List[ExecutionMatch]] = {}
    for m in matches:
        matches_by_trade.setdefault(m.open_execution_id, []).append(m)

    trades: List[Trade] = (
        await session.execute(select(Trade).order_by(Trade.id))
    ).scalars().all()

    lifecycle_rows: List[TradeLifecycleEvent] = []

    for trade in trades:
        trade_matches = matches_by_trade.get(trade.id, [])

        # ── OPENED
        open_exec = executions.get(trade.id)
        opened_at = open_exec.timestamp if open_exec else trade.created_at

        lifecycle_rows.append(
            TradeLifecycleEvent(
                trade_id=trade.id,
                event_type="opened",
                created_at=opened_at,
            )
        )

        # ✅ START WITH ORIGINAL SIZE
        open_qty = Decimal(trade.original_quantity or 0)
        ever_closed = False

        for m in trade_matches:
            close_exec = executions.get(m.close_execution_id)
            if not close_exec:
                continue

            qty = Decimal(m.matched_quantity or 0)
            if qty <= 0:
                continue

            before = open_qty
            open_qty -= qty

            if open_qty < 0:
                open_qty = Decimal("0")

            ts = close_exec.timestamp or trade.created_at

            # ── PARTIAL CLOSE
            if before > 0 and open_qty > 0:
                lifecycle_rows.append(
                    TradeLifecycleEvent(
                        trade_id=trade.id,
                        event_type="partial_close",
                        created_at=ts,
                    )
                )

            # ── FULL CLOSE (emit once)
            if before > 0 and open_qty == 0 and not ever_closed:
                lifecycle_rows.append(
                    TradeLifecycleEvent(
                        trade_id=trade.id,
                        event_type="closed",
                        created_at=ts,
                    )
                )
                ever_closed = True

        # Defensive fallback
        if trade.exit_price is not None and not ever_closed:
            lifecycle_rows.append(
                TradeLifecycleEvent(
                    trade_id=trade.id,
                    event_type="closed",
                    created_at=trade.created_at,
                )
            )

    session.add_all(lifecycle_rows)
    await session.commit()
    return len(lifecycle_rows)


async def main() -> None:
    sessionmaker = get_async_sessionmaker()

    async with sessionmaker() as session:
        count = await rebuild_trade_lifecycle(session)
        print(f"✅ trade_lifecycle_events rebuilt: {count} rows")


if __name__ == "__main__":
    asyncio.run(main())


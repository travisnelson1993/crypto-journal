import asyncio
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_sessionmaker
from app.models.trade_lifecycle_event import TradeLifecycleEvent


async def validate_trade_lifecycle(session: AsyncSession) -> None:
    events = (
        await session.execute(
            select(
                TradeLifecycleEvent.trade_id,
                TradeLifecycleEvent.event_type,
                TradeLifecycleEvent.created_at,
            ).order_by(
                TradeLifecycleEvent.trade_id,
                TradeLifecycleEvent.created_at,
            )
        )
    ).all()

    by_trade = defaultdict(list)
    for trade_id, event_type, ts in events:
        by_trade[trade_id].append((event_type, ts))

    errors = []

    for trade_id, evs in by_trade.items():
        opened = [e for e, _ in evs if e == "opened"]
        closed = [e for e, _ in evs if e == "closed"]

        # 1️⃣ exactly one opened
        if len(opened) != 1:
            errors.append(f"Trade {trade_id}: {len(opened)} opened events")

        # 2️⃣ at most one closed
        if len(closed) > 1:
            errors.append(f"Trade {trade_id}: {len(closed)} closed events")

        # 3️⃣ partial_close must occur before closed
        closed_index = None
        for i, (etype, _) in enumerate(evs):
            if etype == "closed":
                closed_index = i
                break

        if closed_index is not None:
            for etype, _ in evs[closed_index + 1 :]:
                if etype == "partial_close":
                    errors.append(
                        f"Trade {trade_id}: partial_close after closed"
                    )

    if errors:
        print("❌ Lifecycle validation FAILED:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)

    print("✅ Lifecycle validation PASSED — all invariants hold")


async def main():
    sessionmaker = get_async_sessionmaker()
    async with sessionmaker() as session:
        await validate_trade_lifecycle(session)


if __name__ == "__main__":
    asyncio.run(main())

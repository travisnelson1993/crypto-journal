# merge_sweep.py
# Run once to attempt merging existing orphan closes into existing open trades.
import asyncio
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.trade import Trade
from app.api.imports import merge_orphans_into_open

async def sweep():
    async with AsyncSessionLocal() as session:
        q = select(Trade).where(Trade.end_date.is_(None))
        q = q.order_by(Trade.entry_date)
        result = await session.execute(q)
        opens = result.scalars().all()
        total_merged = 0
        total_closed_applied = 0
        for o in opens:
            res = await merge_orphans_into_open(session, o)
            total_merged += res.get("merged_orphans", 0)
            total_closed_applied += res.get("closed_applied", 0)
        await session.commit()
        print(f"Merge sweep complete. merged_orphans={total_merged}, closed_applied={total_closed_applied}")

if __name__ == "__main__":
    asyncio.run(sweep())
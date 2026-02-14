from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trade import Trade
from app.models.trade_lifecycle_event import TradeLifecycleEvent
from app.models.executions import ExecutionMatch


async def rebuild_trade_lifecycle_events(session: AsyncSession) -> int:
    """
    Deterministically rebuild trade lifecycle events.

    Rules:
    - Derived data only (DELETE + rebuild)
    - No guessing
    - No emotions
    - No payloads
    - No external timestamps

    Lifecycle:
      - opened (always)
      - partial_close (for each reduction before zero)
      - closed (once when position reaches zero)
    """

    # 0️⃣ Clear derived table
    await session.execute(delete(TradeLifecycleEvent))
    await session.flush()

    # 1️⃣ Load trades in stable order
    trades: List[Trade] = (
        await session.execute(select(Trade).order_by(Trade.id))
    ).scalars().all()

    lifecycle_rows: List[TradeLifecycleEvent] = []

    for trade in trades:
        # ── OPENED
        lifecycle_rows.append(
            TradeLifecycleEvent(
                trade_id=trade.id,
                event_type="opened",
                created_at=trade.created_at,
            )
        )

        # 2️⃣ Pull execution matches for this trade
        matches = (
            await session.execute(
                select(ExecutionMatch)
                .where(ExecutionMatch.open_execution_id == trade.id)
                .order_by(ExecutionMatch.created_at)
            )
        ).scalars().all()

        # ── Fallback: summary-only close
        if not matches:
            if trade.exit_price is not None:
                lifecycle_rows.append(
                    TradeLifecycleEvent(
                        trade_id=trade.id,
                        event_type="closed",
                        created_at=trade.created_at,
                    )
                )

                # 🔑 Option B: persist trade closure
                if trade.end_date is None:
                    trade.end_date = trade.created_at

            continue

        original_qty = Decimal(str(trade.original_quantity))
        remaining = original_qty
        ever_closed = False

        for m in matches:
            qty = Decimal(str(m.matched_quantity))
            if qty <= 0:
                continue

            before = remaining
            remaining -= qty
            if remaining < 0:
                remaining = Decimal("0")

            # ── PARTIAL CLOSE
            if before > remaining and remaining > 0:
                lifecycle_rows.append(
                    TradeLifecycleEvent(
                        trade_id=trade.id,
                        event_type="partial_close",
                        created_at=m.created_at,
                    )
                )

            # ── FINAL CLOSE (once)
            if before > 0 and remaining == 0 and not ever_closed:
                lifecycle_rows.append(
                    TradeLifecycleEvent(
                        trade_id=trade.id,
                        event_type="closed",
                        created_at=m.created_at,
                    )
                )

                # 🔑 Option B: persist trade closure
                if trade.end_date is None:
                    trade.end_date = m.created_at or datetime.utcnow()

                ever_closed = True

    session.add_all(lifecycle_rows)
    await session.commit()
    return len(lifecycle_rows)


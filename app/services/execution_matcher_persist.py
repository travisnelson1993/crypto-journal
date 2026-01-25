# app/services/execution_matcher_persist.py

from collections import defaultdict, deque
from decimal import Decimal
from sqlalchemy import select, delete

from app.models.executions import Execution
from app.models.execution_match import ExecutionMatch


async def rebuild_execution_matches(session):
    """
    Rebuild execution_matches from executions.

    - Truncates execution_matches
    - Deterministic FIFO matching
    - Inserts (open_execution_id, close_execution_id, matched_quantity)
    - NO trades
    - NO execution updates
    """

    # 0️⃣ Clear derived table (safe + idempotent)
    await session.execute(delete(ExecutionMatch))
    await session.flush()

    # 1️⃣ Load executions deterministically
    result = await session.execute(
        select(Execution).order_by(
            Execution.ticker,
            Execution.direction,
            Execution.timestamp,
            Execution.id,
        )
    )
    executions = result.scalars().all()

    # 2️⃣ Group by (ticker, direction)
    groups = defaultdict(list)
    for e in executions:
        groups[(e.ticker, e.direction)].append(e)

    total_matches = 0

    # 3️⃣ FIFO matching per group
    for (_, _), group in groups.items():
        open_queue = deque()

        for e in group:
            remaining_qty = Decimal(e.quantity)

            if e.side == "OPEN":
                open_queue.append(
                    {
                        "id": e.id,
                        "remaining": remaining_qty,
                    }
                )

            elif e.side == "CLOSE":
                while remaining_qty > 0 and open_queue:
                    open_exec = open_queue[0]

                    matched_qty = min(
                        open_exec["remaining"],
                        remaining_qty,
                    )

                    # 🚫 Guard against dust
                    if matched_qty <= 0:
                        break

                    session.add(
                        ExecutionMatch(
                            open_execution_id=open_exec["id"],
                            close_execution_id=e.id,
                            matched_quantity=matched_qty,
                        )
                    )

                    total_matches += 1

                    open_exec["remaining"] -= matched_qty
                    remaining_qty -= matched_qty

                    if open_exec["remaining"] == 0:
                        open_queue.popleft()

    # 4️⃣ Commit derived results
    await session.commit()

    return total_matches

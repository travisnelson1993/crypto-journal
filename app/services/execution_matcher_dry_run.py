# app/services/execution_matcher_dry_run.py

from collections import defaultdict, deque
from decimal import Decimal
from sqlalchemy import select

from app.models.executions import Execution


class ExecutionMatch:
    def __init__(self, open_id, close_id, quantity):
        self.open_id = open_id
        self.close_id = close_id
        self.quantity = quantity

    def __repr__(self):
        return f"OPEN {self.open_id} -> CLOSE {self.close_id} | qty={self.quantity}"


async def run_dry_run_matcher(session):
    """
    DRY-RUN FIFO execution matcher.

    - Reads executions
    - Deterministic ordering
    - FIFO matching (OPEN -> CLOSE)
    - Handles partial fills
    - Prints matches only
    - Writes NOTHING
    """

    # 1️⃣ Load executions in deterministic order
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

    all_matches = []

    # 3️⃣ FIFO matching per group
    for (ticker, direction), group in groups.items():
        print(f"\n=== Matching {ticker} {direction} ===")

        open_queue = deque()

        for e in group:
            remaining_qty = Decimal(e.quantity)

            if e.side == "OPEN":
                open_queue.append(
                    {
                        "id": e.id,
                        "remaining": remaining_qty,
                        "timestamp": e.timestamp,
                    }
                )

            elif e.side == "CLOSE":
                while remaining_qty > 0 and open_queue:
                    open_exec = open_queue[0]

                    matched_qty = min(
                        open_exec["remaining"],
                        remaining_qty,
                    )

                    # 🚫 Prevent zero / dust matches (Decimal edge case)
                    if matched_qty <= 0:
                        break

                    match = ExecutionMatch(
                        open_id=open_exec["id"],
                        close_id=e.id,
                        quantity=matched_qty,
                    )

                    all_matches.append(match)
                    print(match)

                    # Reduce quantities
                    open_exec["remaining"] -= matched_qty
                    remaining_qty -= matched_qty

                    # Remove fully consumed OPEN
                    if open_exec["remaining"] == 0:
                        open_queue.popleft()

                # CLOSE with no available OPEN inventory
                if remaining_qty > 0:
                    print(
                        f"⚠️  Unmatched CLOSE {e.id} "
                        f"(qty={remaining_qty})"
                    )

        # Remaining OPEN inventory
        for open_exec in open_queue:
            print(
                f"🕒 OPEN {open_exec['id']} still open "
                f"(qty={open_exec['remaining']})"
            )

    # 4️⃣ Summary
    print("\n=== DRY-RUN SUMMARY ===")
    print(f"Total matches: {len(all_matches)}")

    return all_matches

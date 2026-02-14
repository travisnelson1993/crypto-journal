from decimal import Decimal
from sqlalchemy import select, func
from app.models.executions import Execution, ExecutionMatch


async def match_close_execution(session, close_exec: Execution):
    # --- Reconcile close remaining from existing matches (idempotency) ---
    already_matched = await session.scalar(
        select(func.coalesce(func.sum(ExecutionMatch.matched_quantity), 0))
        .where(ExecutionMatch.close_execution_id == close_exec.id)
    )

    expected_remaining = Decimal(close_exec.quantity) - Decimal(already_matched)

    if close_exec.remaining_qty != expected_remaining:
        close_exec.remaining_qty = expected_remaining
        await session.flush()

    if close_exec.remaining_qty <= 0:
        return

    remaining = Decimal(close_exec.remaining_qty)

    # --- Load OPENs FIFO ---
    result = await session.execute(
        select(Execution)
        .where(
            Execution.ticker == close_exec.ticker,
            Execution.side == "OPEN",
            Execution.direction == close_exec.direction,
            Execution.remaining_qty > 0,
        )
        .order_by(Execution.timestamp.asc(), Execution.id.asc())
    )

    opens = result.scalars().all()
    matches: list[tuple[Execution, Decimal]] = []

    # -------- PURE PYTHON FIFO --------
    for open_exec in opens:
        if remaining <= 0:
            break

        open_remaining = Decimal(open_exec.remaining_qty)
        if open_remaining <= 0:
            continue

        match_qty = min(open_remaining, remaining)
        matches.append((open_exec, match_qty))
        remaining -= match_qty

    # -------- APPLY MUTATIONS --------
    for open_exec, match_qty in matches:
        session.add(
            ExecutionMatch(
                close_execution_id=close_exec.id,
                open_execution_id=open_exec.id,
                matched_quantity=match_qty,
            )
        )
        open_exec.remaining_qty -= match_qty

        # 🔑 ensure ORM state is persisted before next open
        await session.flush()

    close_exec.remaining_qty = remaining
    await session.flush()


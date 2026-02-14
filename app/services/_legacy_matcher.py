from sqlalchemy import select

from app.models.executions import Execution, ExecutionMatch


def fifo_match_close(session, close_exec: Execution):
    remaining = close_exec.remaining_qty

    opens = (
        session.execute(
            select(Execution)
            .where(
                Execution.ticker == close_exec.ticker,
                Execution.direction == close_exec.direction,
                Execution.side == "OPEN",
                Execution.remaining_qty > 0,
            )
            .order_by(Execution.timestamp.asc(), Execution.id.asc())
        )
        .scalars()
        .all()
    )

    for open_exec in opens:
        if remaining <= 0:
            break

        match_qty = min(open_exec.remaining_qty, remaining)

        session.add(
            ExecutionMatch(
                close_execution_id=close_exec.id,
                open_execution_id=open_exec.id,
                matched_quantity=match_qty,
            )
        )

        open_exec.remaining_qty -= match_qty
        remaining -= match_qty

    close_exec.remaining_qty = remaining

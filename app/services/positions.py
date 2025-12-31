from sqlalchemy import select, func
from app.models.executions import Execution, ExecutionMatch

def avg_entry_price(session, ticker, direction):
    q = session.execute(
        select(
            func.sum(Execution.price * Execution.quantity) /
            func.sum(Execution.quantity)
        )
        .where(
            Execution.ticker == ticker,
            Execution.direction == direction,
            Execution.side == "OPEN",
        )
    ).scalar()

    return q


def avg_exit_price(session, ticker, direction):
    q = session.execute(
        select(
            func.sum(Execution.price * ExecutionMatch.matched_quantity) /
            func.sum(ExecutionMatch.matched_quantity)
        )
        .join(Execution, Execution.id == ExecutionMatch.close_execution_id)
        .where(
            Execution.ticker == ticker,
            Execution.direction == direction,
        )
    ).scalar()

    return q

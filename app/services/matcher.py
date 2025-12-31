# FIFO matcher and insert helper
# Uses SELECT ... FOR UPDATE SKIP LOCKED when dialect is Postgres
from decimal import Decimal
from sqlalchemy import select, update, func, and_
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session
from app.models.executions import Execution, ExecutionMatch
from app.db import engine  # for detecting dialect

def insert_execution_and_match(db: Session, execution_payload: dict):
    """
    Inserts an execution row (idempotent if source_rowhash provided) and then
    attempts FIFO matching against open executions (SELECT FOR UPDATE SKIP LOCKED on Postgres).
    execution_payload keys: source, source_filename, source_rowhash (optional), source_execution_id,
    ticker, direction, side, quantity (Decimal/str), price (Decimal/str), fee, occurred_at
    Returns the created/loaded Execution instance.
    """
    # idempotency check (by source/source_filename/source_rowhash or source_execution_id)
    if execution_payload.get('source_rowhash'):
        existing = db.execute(
            select(Execution).where(
                Execution.source == execution_payload['source'],
                Execution.source_filename == execution_payload.get('source_filename'),
                Execution.source_rowhash == execution_payload['source_rowhash']
            )
        ).scalars().first()
        if existing:
            return existing

    if execution_payload.get('source_execution_id') and not execution_payload.get('source_rowhash'):
        existing = db.execute(
            select(Execution).where(
                Execution.source == execution_payload['source'],
                Execution.source_execution_id == execution_payload['source_execution_id']
            )
        ).scalars().first()
        if existing:
            return existing

    qty = Decimal(execution_payload.get('quantity'))
    exec_row = Execution(
        source=execution_payload['source'],
        source_filename=execution_payload.get('source_filename'),
        source_rowhash=execution_payload.get('source_rowhash'),
        source_execution_id=execution_payload.get('source_execution_id'),
        ticker=execution_payload['ticker'],
        direction=execution_payload['direction'],
        side=execution_payload['side'],
        quantity=qty,
        remaining_qty=qty,
        price=execution_payload.get('price'),
        fee=execution_payload.get('fee'),
        occurred_at=execution_payload.get('occurred_at'),
    )
    db.add(exec_row)
    db.flush()  # assign id

    # Only try to match when this is a CLOSE side execution
    if exec_row.side == 'CLOSE':
        _match_close_execution(db, exec_row)

    db.commit()
    db.refresh(exec_row)
    return exec_row


def _match_close_execution(db: Session, close_exec: Execution):
    """
    Match a close execution against open executions FIFO.
    Updates remaining_qty on both sides and creates ExecutionMatch rows.
    This uses FOR UPDATE SKIP LOCKED when supported by the DB dialect to safely
    allow concurrent importers.
    """
    dialect_name = engine.dialect.name
    remaining_to_match = close_exec.remaining_qty

    while remaining_to_match > 0:
        # select candidate open executions ordered FIFO (oldest first)
        stmt = select(Execution).where(
            Execution.ticker == close_exec.ticker,
            Execution.side == 'OPEN',
            Execution.remaining_qty > 0
        ).order_by(Execution.occurred_at.asc(), Execution.id.asc())

        # Postgres locking helpers
        if dialect_name == 'postgresql':
            stmt = stmt.with_for_update(skip_locked=True)

        candidate = db.execute(stmt).scalars().first()
        if not candidate:
            # no open executions available - stop
            break

        # determine match quantity
        match_qty = min(candidate.remaining_qty, remaining_to_match)
        match_qty = Decimal(match_qty)

        # create match record
        match = ExecutionMatch(
            open_execution_id=candidate.id,
            close_execution_id=close_exec.id,
            matched_qty=match_qty,
            price=close_exec.price or candidate.price
        )
        db.add(match)

        # decrement remaining_qty on involved executions
        new_candidate_rem = Decimal(candidate.remaining_qty) - match_qty
        new_close_rem = Decimal(remaining_to_match) - match_qty

        # perform updates
        db.execute(
            update(Execution).
            where(Execution.id == candidate.id).
            values(remaining_qty=new_candidate_rem)
        )
        db.execute(
            update(Execution).
            where(Execution.id == close_exec.id).
            values(remaining_qty=new_close_rem)
        )

        # decrease loop counter
        remaining_to_match = new_close_rem

        # flush so other transactions can see changes if needed
        db.flush()

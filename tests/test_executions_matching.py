import decimal
from decimal import Decimal
from datetime import datetime, timezone
import pytest

from app.services.matcher import insert_execution_and_match
from app.models.executions import Execution, ExecutionMatch
from tests.conftest import SessionLocal


def test_basic_open_then_close_matches(db_session):
    # Insert an OPEN execution
    open_payload = {
        'source': 'test',
        'source_filename': 'test.csv',
        'source_rowhash': 'open1',
        'ticker': 'BTC',
        'direction': 'LONG',
        'side': 'OPEN',
        'quantity': Decimal('1.5'),
        'price': Decimal('100.0'),
        'fee': Decimal('0'),
        'occurred_at': datetime.now(timezone.utc),
    }
    open_exec = insert_execution_and_match(db_session, open_payload)
    assert open_exec.remaining_qty == Decimal('1.5')

    # Insert a CLOSE that partially matches
    close_payload = {
        'source': 'test',
        'source_filename': 'test.csv',
        'source_rowhash': 'close1',
        'ticker': 'BTC',
        'direction': 'LONG',
        'side': 'CLOSE',
        'quantity': Decimal('0.5'),
        'price': Decimal('110.0'),
        'fee': Decimal('0'),
        'occurred_at': datetime.now(timezone.utc),
    }
    close_exec = insert_execution_and_match(db_session, close_payload)

    # After matching, open should have remaining 1.0
    refreshed_open = db_session.get(Execution, open_exec.id)
    assert refreshed_open.remaining_qty == Decimal('1.0')

    # close remaining should be 0
    refreshed_close = db_session.get(Execution, close_exec.id)
    assert refreshed_close.remaining_qty == Decimal('0')

    # check match record
    matches = db_session.execute(
        db_session.query(ExecutionMatch).filter(ExecutionMatch.close_execution_id == close_exec.id)
    ).scalars().all()
    assert len(matches) >= 1
    assert matches[0].matched_qty == Decimal('0.5')


def test_idempotency_on_same_rowhash(db_session):
    payload = {
        'source': 'test',
        'source_filename': 'test.csv',
        'source_rowhash': 'idemp-1',
        'ticker': 'ETH',
        'direction': 'LONG',
        'side': 'OPEN',
        'quantity': Decimal('2.0'),
        'price': Decimal('50.0'),
        'fee': Decimal('0'),
        'occurred_at': datetime.now(timezone.utc),
    }
    e1 = insert_execution_and_match(db_session, payload)
    e2 = insert_execution_and_match(db_session, payload)
    assert e1.id == e2.id

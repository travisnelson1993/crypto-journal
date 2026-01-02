from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.executions import Execution
from app.services.matcher import fifo_match_close


@pytest.fixture
def session():
    # Use an in-memory SQLite DB for isolated unit tests
    engine = create_engine("sqlite:///:memory:", future=True)
    # Create tables for the models (Base was added to app.db.database)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    try:
        yield sess
    finally:
        sess.close()


def test_fifo_partial_close(session):
    open1 = Execution(
        source="test",
        ticker="BTCUSDT",
        side="OPEN",
        direction="LONG",
        price=Decimal("100"),
        quantity=Decimal("2"),
        remaining_qty=Decimal("2"),
        timestamp=datetime.now(timezone.utc),
    )

    close1 = Execution(
        source="test",
        ticker="BTCUSDT",
        side="CLOSE",
        direction="LONG",
        price=Decimal("110"),
        quantity=Decimal("1"),
        remaining_qty=Decimal("1"),
        timestamp=datetime.now(timezone.utc),
    )

    session.add_all([open1, close1])
    session.commit()

    fifo_match_close(session, close1)
    session.commit()

    assert open1.remaining_qty == Decimal("1")
    assert close1.remaining_qty == Decimal("0")

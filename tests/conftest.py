import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base  # adjust if your project has Base elsewhere

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(scope='session')
def db_engine():
    # Create schema for tests
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(db_engine):
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()

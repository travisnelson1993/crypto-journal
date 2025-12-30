import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Default to in-memory SQLite for quick local tests. Set DATABASE_URL for Postgres/CI:
# e.g. export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/test_db
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

# Engine & session factory (future=True for SQLAlchemy 1.4+ style)
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Declarative Base
Base = declarative_base()


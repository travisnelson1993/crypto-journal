from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)

    ticker = Column(String, nullable=False)
    direction = Column(String(16), nullable=True)

    entry_price = Column(Numeric(18, 8), nullable=True)
    exit_price = Column(Numeric(18, 8), nullable=True)
    stop_loss = Column(Numeric(18, 8), nullable=True)

    leverage = Column(Integer, nullable=False, server_default="1")

    entry_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    entry_summary = Column(Text, nullable=True)

    orphan_close = Column(Boolean, nullable=False, server_default="false")
    is_duplicate = Column(Boolean, nullable=False, server_default="false")

    source = Column(String, nullable=True)
    source_filename = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImportedFile(Base):
    __tablename__ = "imported_files"

    id = Column(Integer, primary_key=True)

    filename = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, unique=True)

    imported_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

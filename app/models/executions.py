from sqlalchemy import (
    Column, Integer, String, Numeric, Enum, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from app.db.database import Base
from sqlalchemy.sql import func

class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    source_filename = Column(String)
    ticker = Column(String, nullable=False)

    side = Column(Enum("OPEN", "CLOSE", name="exec_side"), nullable=False)
    direction = Column(Enum("LONG", "SHORT", name="exec_direction"), nullable=False)

    price = Column(Numeric(18, 8), nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    remaining_qty = Column(Numeric(18, 8), nullable=False)

    timestamp = Column(DateTime(timezone=True), nullable=False)
    fee = Column(Numeric(18, 8), default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExecutionMatch(Base):
    __tablename__ = "execution_matches"

    id = Column(Integer, primary_key=True)
    close_execution_id = Column(Integer, ForeignKey("executions.id"))
    open_execution_id = Column(Integer, ForeignKey("executions.id"))
    matched_quantity = Column(Numeric(18, 8), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

# SQLAlchemy models for executions, execution_matches, and positions
# Adjust Base import to match your project (e.g. from app.db import Base)
from sqlalchemy import Column, Integer, BigInteger, String, Numeric, Enum, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db import Base  # <-- adjust if your Base is elsewhere (e.g., from app.models.meta import Base)

DirectionEnum = Enum('LONG', 'SHORT', name='direction_enum')
SideEnum = Enum('OPEN', 'CLOSE', name='side_enum')


class Execution(Base):
    __tablename__ = 'executions'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False)
    source_filename = Column(String(255), nullable=True)
    source_rowhash = Column(String(64), nullable=True, index=False)
    source_execution_id = Column(String(128), nullable=True)
    ticker = Column(String(32), nullable=False, index=True)
    direction = Column(DirectionEnum, nullable=False)
    side = Column(SideEnum, nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    remaining_qty = Column(Numeric(18, 8), nullable=False)
    price = Column(Numeric(30, 12), nullable=True)
    fee = Column(Numeric(30, 12), nullable=True)
    occurred_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    # relationships
    matches_open = relationship('ExecutionMatch', foreign_keys='ExecutionMatch.open_execution_id', back_populates='open_execution')
    matches_close = relationship('ExecutionMatch', foreign_keys='ExecutionMatch.close_execution_id', back_populates='close_execution')


class ExecutionMatch(Base):
    __tablename__ = 'execution_matches'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    open_execution_id = Column(BigInteger, ForeignKey('executions.id', ondelete='CASCADE'), nullable=False)
    close_execution_id = Column(BigInteger, ForeignKey('executions.id', ondelete='CASCADE'), nullable=False)
    matched_qty = Column(Numeric(18, 8), nullable=False)
    price = Column(Numeric(30, 12), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    open_execution = relationship('Execution', foreign_keys=[open_execution_id], back_populates='matches_open')
    close_execution = relationship('Execution', foreign_keys=[close_execution_id], back_populates='matches_close')


class Position(Base):
    __tablename__ = 'positions'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticker = Column(String(32), nullable=False, unique=True)
    quantity = Column(Numeric(30, 12), nullable=False, server_default='0')
    avg_price = Column(Numeric(30, 12), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
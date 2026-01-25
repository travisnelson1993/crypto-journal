# app/models/execution_match.py

from sqlalchemy import Column, ForeignKey, Integer, Numeric
from sqlalchemy.orm import relationship

from app.db.database import Base


class ExecutionMatch(Base):
    __tablename__ = "execution_matches"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)

    open_execution_id = Column(
        Integer,
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    close_execution_id = Column(
        Integer,
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    matched_quantity = Column(
        Numeric(precision=36, scale=8),
        nullable=False,
    )

    # Optional relationships (safe, not used yet)
    open_execution = relationship(
        "Execution",
        foreign_keys=[open_execution_id],
        lazy="joined",
    )

    close_execution = relationship(
        "Execution",
        foreign_keys=[close_execution_id],
        lazy="joined",
    )

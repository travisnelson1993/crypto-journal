# app/models/trade_lifecycle_event.py

import uuid
from sqlalchemy import Column, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID, ENUM

from app.db.database import Base

trade_lifecycle_event_enum = ENUM(
    "opened",
    "partial_close",
    "closed",
    name="trade_lifecycle_event_enum",
    create_type=False,
)

class TradeLifecycleEvent(Base):
    __tablename__ = "trade_lifecycle_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    trade_id = Column(Integer, nullable=False, index=True)

    event_type = Column(trade_lifecycle_event_enum, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

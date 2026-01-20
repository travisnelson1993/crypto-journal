import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, Numeric, Text, String
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.database import Base

class TradeEntryNote(Base):
    __tablename__ = "trade_entry_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(Integer, nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    entry_reasons = Column(JSONB, nullable=False)
    strategy = Column(String, nullable=True)
    risk_pct = Column(Numeric(5, 2), nullable=True)
    confidence_at_entry = Column(Integer, nullable=True)

    optional_comment = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

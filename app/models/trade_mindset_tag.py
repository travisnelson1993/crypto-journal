import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.database import Base

class TradeMindsetTag(Base):
    __tablename__ = "trade_mindset_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(Integer, nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    tags = Column(JSONB, nullable=False)
    optional_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

import uuid
from datetime import datetime, date
from sqlalchemy import Column, Date, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM

from app.db.database import Base

daily_bias_enum = ENUM(
    "bullish", "bearish", "neutral", "range",
    name="daily_bias_enum",
    create_type=False
)

class DailyJournal(Base):
    __tablename__ = "daily_journals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    journal_date = Column(Date, nullable=False)

    sleep_quality = Column(Integer, nullable=False)
    energy_level = Column(Integer, nullable=False)
    confidence_level = Column(Integer, nullable=False)
    emotional_intensity = Column(Integer, nullable=False)

    daily_bias = Column(daily_bias_enum, nullable=False)

    emotional_tags = Column(JSONB, nullable=True)
    optional_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

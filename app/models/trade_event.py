import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM

from app.db.database import Base

trade_event_type_enum = ENUM(
    "hold", "partial", "move_sl", "scale_in", "exit_early",
    name="trade_event_type_enum",
    create_type=False
)

trade_event_reason_enum = ENUM(
    "plan_based", "emotion_based", "external_signal",
    name="trade_event_reason_enum",
    create_type=False
)

trade_emotion_enum = ENUM(
    "calm", "fear", "greed", "doubt", "impatience",
    name="trade_emotion_enum",
    create_type=False
)

class TradeEvent(Base):
    __tablename__ = "trade_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(Integer, nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    event_type = Column(trade_event_type_enum, nullable=False)
    reason = Column(trade_event_reason_enum, nullable=False)

    emotion = Column(trade_emotion_enum, nullable=True)
    emotion_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

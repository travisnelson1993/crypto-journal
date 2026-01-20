import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, ENUM

from app.db.database import Base

exit_type_enum = ENUM(
    "tp", "sl", "manual", "early",
    name="exit_type_enum",
    create_type=False
)

violation_reason_enum = ENUM(
    "fomo", "loss_aversion", "doubt", "impatience",
    name="violation_reason_enum",
    create_type=False
)

would_take_again_enum = ENUM(
    "yes", "no", "with_changes",
    name="would_take_again_enum",
    create_type=False
)

class TradeExitNote(Base):
    __tablename__ = "trade_exit_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(Integer, nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    exit_type = Column(exit_type_enum, nullable=False)
    plan_followed = Column(Integer, nullable=False)

    violation_reason = Column(violation_reason_enum, nullable=True)
    would_take_again = Column(would_take_again_enum, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

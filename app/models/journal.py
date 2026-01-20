import enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    Text,
    Enum,
)
from sqlalchemy.sql import func
from app.db.database import Base


# -------------------------
# ENUMS (Python)
# -------------------------
class EmotionalState(str, enum.Enum):
    focused = "focused"
    calm = "calm"
    confident = "confident"
    neutral = "neutral"
    impatient = "impatient"
    anxious = "anxious"
    fearful = "fearful"
    greedy = "greedy"
    tired = "tired"
    distracted = "distracted"
    overconfident = "overconfident"


class DailyBias(str, enum.Enum):
    bullish = "bullish"
    bearish = "bearish"
    range = "range"


# -------------------------
# DAILY JOURNAL
# -------------------------
class DailyJournalEntry(Base):
    __tablename__ = "daily_journal_entries"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)

    sleep_quality = Column(Integer, nullable=False)
    energy_level = Column(Integer, nullable=False)

    emotional_state = Column(
        Enum(
            EmotionalState,
            name="emotional_state_enum",   # ✅ MUST MATCH DB
            native_enum=True,
        ),
        nullable=False,
    )

    daily_bias = Column(
        Enum(
            DailyBias,
            name="daily_bias_enum",        # ✅ MUST MATCH DB
            native_enum=True,
        ),
        nullable=False,
    )

    confidence = Column(Integer, nullable=False)
    notes = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# -------------------------
# TRADE NOTES (Phase 2A)
# -------------------------
class TradeNote(Base):
    __tablename__ = "trade_notes"

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=False)

    note_type = Column(String, nullable=False)  # entry / mid / exit
    content = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

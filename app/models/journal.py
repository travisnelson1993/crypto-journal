# app/models/journal.py

from app.models.trade import Trade  # noqa: F401  <-- MUST be at top

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


# 🔒 Phase 2B — Trade Note Type Enum
class TradeNoteType(str, enum.Enum):
    entry = "entry"
    mid = "mid"
    exit = "exit"


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
# TRADE NOTES (Phase 2B)
# -------------------------
class TradeNote(Base):
    __tablename__ = "trade_notes"

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=False)

    note_type = Column(
        Enum(
            TradeNoteType,
            name="trade_note_type_enum",   # 🔒 DB ENUM (next step)
            native_enum=True,
        ),
        nullable=False,
    )

    content = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

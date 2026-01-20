from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field
from app.models.journal import TradeNoteType


# -------------------------
# ENUMS
# -------------------------
class EmotionalState(str, Enum):
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


class DailyBias(str, Enum):
    bullish = "bullish"
    bearish = "bearish"
    range = "range"


# -------------------------
# DAILY JOURNAL
# -------------------------
class DailyJournalCreate(BaseModel):
    date: date

    sleep_quality: int = Field(ge=1, le=10)
    energy_level: int = Field(ge=1, le=10)
    confidence: int = Field(ge=1, le=10)

    emotional_state: EmotionalState
    daily_bias: DailyBias

    notes: str | None = None


class DailyJournalOut(DailyJournalCreate):
    id: int

    class Config:
        from_attributes = True


# -------------------------
# TRADE NOTES (Phase 2B)
# -------------------------
class TradeNoteCreate(BaseModel):
    note_type: TradeNoteType
    content: str | None = None


class TradeNoteOut(BaseModel):
    id: int
    trade_id: int
    note_type: TradeNoteType
    content: str | None
    created_at: datetime

    class Config:
        from_attributes = True

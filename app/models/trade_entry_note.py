import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    Text,
    String,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict

from app.db.database import Base


# CATEGORY 5 — ENTRY INTENT (Advisory)
# This model represents trader intent at or before entry time.
# It may be created after entry, but late creation is treated as behavioral data.
# No enforcement logic belongs here.
class TradeEntryNote(Base):
    __tablename__ = "trade_entry_notes"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    trade_id = Column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # -------------------------------------------------
    # Entry rationale (DB-portable JSON)
    # -------------------------------------------------
    entry_reasons = Column(
        MutableDict.as_mutable(
            JSONB().with_variant(JSON, "sqlite")
        ),
        nullable=False,
    )

    # -------------------------------------------------
    # Strategy metadata (planned, not realized)
    # -------------------------------------------------
    strategy = Column(String, nullable=True)
    planned_risk_pct = Column(Numeric(5, 2), nullable=True)
    confidence_at_entry = Column(Integer, nullable=True)

    optional_comment = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

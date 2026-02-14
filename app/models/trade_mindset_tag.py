import enum
from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM

from app.db.database import Base


# -------------------------
# ENUM
# -------------------------
class TradeMindsetTagType(str, enum.Enum):
    fomo = "fomo"
    revenge = "revenge"
    hesitation = "hesitation"
    overconfidence = "overconfidence"
    fear = "fear"
    discipline = "discipline"
    patience = "patience"
    impulsive = "impulsive"


# -------------------------
# MODEL
# -------------------------
class TradeMindsetTag(Base):
    __tablename__ = "trade_mindset_tags"

    id = Column(Integer, primary_key=True)

    trade_note_id = Column(
        Integer,
        ForeignKey("trade_notes.id", ondelete="CASCADE"),
        nullable=False,
    )

    tag = Column(
        ENUM(
            TradeMindsetTagType,
            name="trade_mindset_tag_enum",
            create_type=False,  # 🔒 Alembic owns enum lifecycle
        ),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


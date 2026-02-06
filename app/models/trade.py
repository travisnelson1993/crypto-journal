from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Numeric,
    func,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # -------------------------------------------------
    # Core identity
    # -------------------------------------------------
    ticker: Mapped[str] = mapped_column(String(30), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # long / short

    # -------------------------------------------------
    # Quantity tracking
    # -------------------------------------------------
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )
    original_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )

    # -------------------------------------------------
    # Pricing
    # -------------------------------------------------
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )
    exit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )

    # -------------------------------------------------
    # Fees & realized performance
    # -------------------------------------------------
    fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    realized_pnl_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )

    # -------------------------------------------------
    # Risk & sizing
    # -------------------------------------------------
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    leverage: Mapped[float] = mapped_column(
        Float,
        server_default="1",
        nullable=False,
    )

    # -------------------------------------------------
    # Advisory & planning (portable JSON)
    # -------------------------------------------------
    risk_warnings: Mapped[Optional[dict]] = mapped_column(
        MutableDict.as_mutable(
            JSONB().with_variant(JSON, "sqlite")
        ),
        nullable=True,
    )

    trade_plan: Mapped[Optional[dict]] = mapped_column(
        MutableDict.as_mutable(
            JSONB().with_variant(JSON, "sqlite")
        ),
        nullable=True,
    )

    # -------------------------------------------------
    # Metadata
    # -------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -------------------------------------------------
    # Quality-of-life helpers
    # -------------------------------------------------
    @property
    def has_risk_warnings(self) -> bool:
        return bool(self.risk_warnings)


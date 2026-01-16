from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Numeric,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # -------------------------------------------------
    # Core identity
    # -------------------------------------------------
    ticker: Mapped[str] = mapped_column(String(30), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # long / short

    # -------------------------------------------------
    # Quantity tracking (CRITICAL)
    # -------------------------------------------------
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )

    # ✅ ORIGINAL position size (never changes)
    original_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )

    # -------------------------------------------------
    # Pricing
    # -------------------------------------------------
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )
    exit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )

    # -------------------------------------------------
    # Fees
    # -------------------------------------------------
    fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0")
    )

    # -------------------------------------------------
    # REALIZED PERFORMANCE (locked on close)
    # -------------------------------------------------
    realized_pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    realized_pnl_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )

    # -------------------------------------------------
    # Risk & sizing (trade-defined)
    # -------------------------------------------------
    stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    leverage: Mapped[float] = mapped_column(Float, default=1.0)

    # -------------------------------------------------
    # Equity snapshot at entry (Step 1.5)
    # -------------------------------------------------
    # These fields are IMMUTABLE once set.
    # They enable true % risk, USD equity curve, and prop-style rules.
    account_equity_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    risk_usd_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    risk_pct_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )

    # -------------------------------------------------
    # Timing
    # -------------------------------------------------
    entry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # -------------------------------------------------
    # Metadata
    # -------------------------------------------------
    entry_summary: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    orphan_close: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

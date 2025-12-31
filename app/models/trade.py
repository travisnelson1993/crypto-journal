from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, DateTime, func, Integer, Boolean
from app.db.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Core fields (match your sheet)
    ticker: Mapped[str] = mapped_column(String(30), index=True)  # BTC, ETH, etc.
    direction: Mapped[str] = mapped_column(String(10))  # LONG / SHORT / SPOT (if you use it)

    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)

    leverage: Mapped[float] = mapped_column(Float, default=1.0)

    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entry_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ✅ NEW: track import/orphans so a later CSV can “complete” trades
    orphan_close: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

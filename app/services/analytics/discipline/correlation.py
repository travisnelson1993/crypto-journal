from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discipline_snapshot import DisciplineSnapshot
from app.models.trade import Trade

from app.schemas.analytics.discipline_correlation import (
    DisciplineCorrelationResponse,
    GradeCorrelationStats,
    DisciplineCorrelationSummary,
)


Period = Literal["7d", "30d"]


def _days_for_period(period: Period) -> int:
    return 7 if period == "7d" else 30


async def get_discipline_performance_correlation(
    *,
    db: AsyncSession,
    period: Period = "30d",
) -> DisciplineCorrelationResponse:
    """
    Correlate discipline grades to performance outcomes.
    Advisory-only, read-only.
    """

    start_date = date.today() - timedelta(days=_days_for_period(period) - 1)

    # -------------------------------------------------
    # Pull Discipline Snapshots
    # -------------------------------------------------

    snapshots = (
        await db.execute(
            select(DisciplineSnapshot)
            .where(DisciplineSnapshot.snapshot_date >= start_date)
        )
    ).scalars().all()

    if not snapshots:
        return DisciplineCorrelationResponse(
            period=period,
            by_grade={},
            summary=DisciplineCorrelationSummary(
                high_discipline_avg_r=0,
                low_discipline_avg_r=0,
            ),
        )

    snapshots_by_date = {
        s.snapshot_date: s.grade for s in snapshots
    }

    # -------------------------------------------------
    # Pull Trades
    # -------------------------------------------------

    trades = (
        await db.execute(
            select(Trade)
            .where(Trade.created_at >= start_date)
        )
    ).scalars().all()

    stats: dict[str, dict[str, float | int]] = {}

    # -------------------------------------------------
    # Correlate Trades to Snapshot Grade
    # -------------------------------------------------

    for trade in trades:
        trade_date = trade.created_at.date()
        grade = snapshots_by_date.get(trade_date)

        if not grade:
            continue

        bucket = stats.setdefault(
            grade,
            {"trade_count": 0, "wins": 0, "total_r": 0.0},
        )

        bucket["trade_count"] += 1

        pct = float(trade.realized_pnl_pct or 0)
        bucket["total_r"] += pct

        if pct > 0:
            bucket["wins"] += 1

    # -------------------------------------------------
    # Build Typed Response
    # -------------------------------------------------

    by_grade: dict[str, GradeCorrelationStats] = {}

    for grade, data in stats.items():
        trade_count = int(data["trade_count"])

        by_grade[grade] = GradeCorrelationStats(
            trade_count=trade_count,
            win_rate=round(data["wins"] / trade_count, 2)
            if trade_count
            else 0,
            avg_r=round(data["total_r"] / trade_count, 4)
            if trade_count
            else 0,
        )

    # -------------------------------------------------
    # High vs Low Discipline Summary
    # -------------------------------------------------

    high = [v.avg_r for g, v in by_grade.items() if g in ("A", "B")]
    low = [v.avg_r for g, v in by_grade.items() if g in ("C", "D", "F")]

    return DisciplineCorrelationResponse(
        period=period,
        by_grade=by_grade,
        summary=DisciplineCorrelationSummary(
            high_discipline_avg_r=round(sum(high) / len(high), 4)
            if high
            else 0,
            low_discipline_avg_r=round(sum(low) / len(low), 4)
            if low
            else 0,
        ),
    )


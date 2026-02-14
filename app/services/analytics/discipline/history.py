from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discipline_snapshot import DisciplineSnapshot


Period = Literal["7d", "30d"]


def _days_for_period(period: Period) -> int:
    return 7 if period == "7d" else 30


async def get_discipline_history(
    *,
    db: AsyncSession,
    period: Period = "30d",
) -> Dict[str, Any]:
    """
    Read-only discipline history from persisted snapshots.

    Returns:
    {
      "period": "7d"|"30d",
      "average_score": int,
      "grade_distribution": {"A": int, ...},
      "trend": [{"date": "YYYY-MM-DD", "score": int, "grade": str}],
      "top_coaching_flags": [{"flag": str, "count": int}],
      "sparklines": {
          "scores": [int, ...],
          "grades": [str, ...]
      }
    }
    """
    days = _days_for_period(period)
    start_date = date.today() - timedelta(days=days - 1)

    rows = (
        await db.execute(
            select(DisciplineSnapshot)
            .where(DisciplineSnapshot.snapshot_date >= start_date)
            .order_by(DisciplineSnapshot.snapshot_date.desc())
        )
    ).scalars().all()

    if not rows:
        return {
            "period": period,
            "average_score": 0,
            "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
            "trend": [],
            "top_coaching_flags": [],
            "sparklines": {
                "scores": [],
                "grades": [],
            },
        }

    scores = [r.discipline_score for r in rows]
    avg_score = int(round(sum(scores) / len(scores)))

    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in rows:
        g = (r.grade or "").strip().upper()
        if g in grade_distribution:
            grade_distribution[g] += 1

    trend: List[Dict[str, Any]] = [
        {
            "date": r.snapshot_date.isoformat(),
            "score": r.discipline_score,
            "grade": r.grade,
        }
        for r in rows
    ]

    # Count coaching flags frequency
    flag_counts: Dict[str, int] = {}
    for r in rows:
        flags = r.coaching_flags or []
        for f in flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

    top_coaching_flags = [
        {"flag": k, "count": v}
        for k, v in sorted(flag_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Sparkline-ready arrays (oldest → newest)
    chronological = list(reversed(rows))

    return {
        "period": period,
        "average_score": avg_score,
        "grade_distribution": grade_distribution,
        "trend": trend,
        "top_coaching_flags": top_coaching_flags,
        "sparklines": {
            "scores": [r.discipline_score for r in chronological],
            "grades": [r.grade for r in chronological],
        },
    }

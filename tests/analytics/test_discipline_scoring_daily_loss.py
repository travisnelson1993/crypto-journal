import pytest

from app.services.analytics.discipline.scoring import compute_discipline_score


@pytest.mark.asyncio
async def test_discipline_score_daily_max_loss_breach():
    """
    Breaching the daily max loss is a severe discipline violation
    and should heavily reduce the discipline score.
    """

    result = await compute_discipline_score(
        risk_warnings=[],
        entry_intent={
            "missing": False,
            "late": False,
        },
        loss_streaks={
            "current_streak": 1,
            "severity": None,
        },
        daily_max_loss={
            "breached": True,
        },
    )

    # --- Core contract ---
    assert "discipline_score" in result
    assert "penalties" in result
    assert "grade" in result

    # --- Capital protection penalty ---
    penalty_reasons = [p["reason"] for p in result["penalties"]]

    assert "Daily max loss breached" in penalty_reasons

    # --- Severity check ---
    assert result["discipline_score"] <= 80
    assert result["grade"] in {"C", "D", "F"}

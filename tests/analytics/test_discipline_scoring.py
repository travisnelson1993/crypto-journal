import pytest

from app.services.analytics.discipline.scoring import compute_discipline_score


@pytest.mark.asyncio
async def test_discipline_score_basic_penalties():
    """
    A trade day with multiple advisory violations should
    reduce the discipline score in a transparent way.
    """

    # --- Simulated analytics outputs ---
    risk_warnings = [
        {
            "type": "MISSING_STOP",
            "severity": "HIGH",
            "message": "Trade entered without a stop-loss.",
            "confidence": 0.9,
        },
        {
            "type": "RISK_TOO_HIGH",
            "severity": "MEDIUM",
            "message": "Risk exceeds 2% guidance.",
            "confidence": 0.8,
        },
    ]

    entry_intent = {
        "missing": True,
        "late": False,
    }

    loss_streaks = {
        "current_streak": 3,
        "severity": "MEDIUM",
    }

    daily_max_loss = {
        "breached": False,
    }

    # --- Compute discipline score ---
    result = await compute_discipline_score(
        risk_warnings=risk_warnings,
        entry_intent=entry_intent,
        loss_streaks=loss_streaks,
        daily_max_loss=daily_max_loss,
    )

    # --- Core contract ---
    assert "discipline_score" in result
    assert "grade" in result
    assert "penalties" in result
    assert "summary" in result

    # --- Scoring expectations ---
    assert result["discipline_score"] < 100
    assert result["discipline_score"] >= 0

    # --- Penalty transparency ---
    penalty_reasons = [p["reason"] for p in result["penalties"]]

    assert "Missing stop-loss" in penalty_reasons
    assert "Risk exceeds recommended percentage" in penalty_reasons
    assert "Loss streak detected (MEDIUM)" in penalty_reasons

    # --- Grade sanity check ---
    assert result["grade"] in {"A", "B", "C", "D", "F"}

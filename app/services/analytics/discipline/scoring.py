from typing import List, Dict, Any


async def compute_discipline_score(
    *,
    risk_warnings: List[Dict[str, Any]],
    entry_intent: Dict[str, bool],
    loss_streaks: Dict[str, Any],
    daily_max_loss: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute an advisory-only discipline score based on analytics outputs.
    No enforcement. No DB access. Pure interpretation layer.
    """

    score = 100
    penalties = []

    # -------------------------------------------------
    # Risk planning discipline
    # -------------------------------------------------
    for warning in risk_warnings:
        w_type = warning.get("type")

        if w_type == "MISSING_STOP":
            penalties.append({
                "category": "Risk Planning",
                "reason": "Missing stop-loss",
                "points": -15,
            })
            score -= 15

        elif w_type == "RISK_TOO_HIGH":
            penalties.append({
                "category": "Risk Planning",
                "reason": "Risk exceeds recommended percentage",
                "points": -10,
            })
            score -= 10

    # -------------------------------------------------
    # Process discipline
    # -------------------------------------------------
    if entry_intent.get("missing"):
        penalties.append({
            "category": "Process",
            "reason": "Missing entry intent",
            "points": -10,
        })
        score -= 10

    if entry_intent.get("late"):
        penalties.append({
            "category": "Process",
            "reason": "Late entry intent",
            "points": -5,
        })
        score -= 5

    # -------------------------------------------------
    # Psychological risk signals
    # -------------------------------------------------
    streak_severity = loss_streaks.get("severity")

    if streak_severity == "LOW":
        penalties.append({
            "category": "Psychological",
            "reason": "Loss streak detected (LOW)",
            "points": -5,
        })
        score -= 5

    elif streak_severity == "MEDIUM":
        penalties.append({
            "category": "Psychological",
            "reason": "Loss streak detected (MEDIUM)",
            "points": -10,
        })
        score -= 10

    elif streak_severity == "HIGH":
        penalties.append({
            "category": "Psychological",
            "reason": "Loss streak detected (HIGH)",
            "points": -15,
        })
        score -= 15

    # -------------------------------------------------
    # Capital protection discipline
    # -------------------------------------------------
    if daily_max_loss.get("breached"):
        penalties.append({
            "category": "Capital Protection",
            "reason": "Daily max loss breached",
            "points": -20,
        })
        score -= 20

    # -------------------------------------------------
    # Clamp score
    # -------------------------------------------------
    score = max(score, 0)

    # -------------------------------------------------
    # Grade mapping
    # -------------------------------------------------
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    # -------------------------------------------------
    # Capital protection override
    # -------------------------------------------------
    if daily_max_loss.get("breached") and grade in {"A", "B"}:
        grade = "C"

    summary = (
        "High discipline" if score >= 90 else
        "Moderate discipline" if score >= 75 else
        "Inconsistent discipline" if score >= 60 else
        "Emotion-driven behavior"
    )

    return {
        "discipline_score": score,
        "grade": grade,
        "penalties": penalties,
        "summary": summary,
    }

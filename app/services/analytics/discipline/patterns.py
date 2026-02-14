"""
Behavioral pattern detection.
Advisory only. No enforcement.
"""

from typing import List, Dict, Any


async def detect_behavioral_patterns(
    *,
    risk_warnings: list,
    entry_intent: Dict[str, Any],
    loss_streaks: Dict[str, Any],
    daily_max_loss: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """
    Detect behavioral trading patterns based on risk signals.
    Returns a list of detected patterns with confidence and evidence.
    """

    patterns: List[Dict[str, Any]] = []

    # -------------------------------------------------
    # Impulsive entry (missing plan)
    # -------------------------------------------------
    if entry_intent.get("missing"):
        patterns.append({
            "type": "IMPULSIVE_ENTRY",
            "confidence": 0.7,
            "evidence": [
                "Entry intent missing at time of execution",
            ],
        })

    # -------------------------------------------------
    # Revenge trading (loss streak driven behavior)
    # -------------------------------------------------
    if loss_streaks.get("current_streak", 0) >= 3:
        severity = loss_streaks.get("severity")

        evidence = [
            f"Loss streak of {loss_streaks.get('current_streak')} trades",
        ]

        if severity:
            evidence.append(f"Loss streak severity: {severity}")

        patterns.append({
            "type": "REVENGE_TRADING",
            "confidence": 0.8 if severity in {"MEDIUM", "HIGH"} else 0.7,
            "evidence": evidence,
        })

    return patterns

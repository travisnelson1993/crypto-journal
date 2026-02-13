# app/services/analytics/discipline/coaching.py

from typing import List, Dict, Any


# -------------------------------------------------
# Coaching rule table
# -------------------------------------------------
# Each rule maps a detected behavioral pattern
# to a primary coaching action plus metadata.
#
# Advisory only — no enforcement.
# -------------------------------------------------

COACHING_RULES = {
    "REVENGE_TRADING": {
        "action": "cooldown",
        "flags": ["TAKE_A_BREAK", "REDUCE_SIZE"],
        "message": (
            "Signs of revenge trading detected. "
            "Pause trading and review recent losses, reduce size, "
            "and reset emotionally before entering another position."
        ),
    },
    "IMPULSIVE_ENTRY": {
        "action": "plan_first",
        "flags": ["PLAN_BEFORE_ENTRY"],
        "message": (
            "Impulsive entry detected. "
            "Write an entry plan before executing the next trade."
        ),
    },
    "LOSS_STREAK_PRESSURE": {
        "action": "slow_down",
        "flags": ["REDUCE_RISK", "SLOW_DOWN"],
        "message": (
            "Loss streak pressure detected. "
            "Lower risk per trade and slow execution tempo."
        ),
    },
    "DAILY_MAX_LOSS_BREACH": {
        "action": "stop_trading",
        "flags": ["STOP_TRADING_TODAY"],
        "message": (
            "Daily loss limit breached. "
            "Stop trading for the day to protect capital."
        ),
    },
}


def attach_coaching_messages(
    patterns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Attach coaching guidance to detected behavioral patterns.

    Returns one entry per pattern:

    {
        "type": "...",
        "confidence": 0.8,
        "evidence": [...],
        "coaching": {
            "action": "cooldown",
            "flags": [...],
            "message": "..."
        }
    }

    ❌ No enforcement
    ❌ No trade blocking
    ✅ Awareness + self-coaching
    """

    coached: List[Dict[str, Any]] = []
    seen_types = set()

    for pattern in patterns or []:
        pattern_type = pattern.get("type")
        if not pattern_type or pattern_type in seen_types:
            continue

        rule = COACHING_RULES.get(pattern_type)
        if not rule:
            continue

        coached.append({
            "type": pattern_type,
            "confidence": pattern.get("confidence"),
            "evidence": pattern.get("evidence", []),
            "coaching": {
                "action": rule.get("action"),
                "flags": rule.get("flags", []),
                "message": rule.get("message", ""),
            },
        })

        seen_types.add(pattern_type)

    return coached

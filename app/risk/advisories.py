from typing import Dict, Any, Optional, List

from app.models.trade import Trade
from app.risk.codes import (
    EXPOSURE_NO_STOP,
    MAX_RISK_PCT,
)

ENGINE_EQUITY_SNAPSHOT = "equity_snapshot_v1"


# =================================================
# CANONICAL ADVISORY ENGINE (ENTRYPOINT)
# =================================================
def compute_risk_advisories(trade: Trade) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Returns lifecycle-keyed, append-only risk advisories.

    Final, UI-safe schema:
    {
      "equity_snapshot": [ {...}, {...} ],
      "entry_advisory":  [ {...} ]
    }
    """

    warnings: Dict[str, List[Dict[str, Any]]] = {}

    equity_snapshot = build_equity_snapshot_warnings(trade)
    if equity_snapshot:
        warnings["equity_snapshot"] = equity_snapshot

    return warnings or None


# =================================================
# EQUITY SNAPSHOT RULES (IMMUTABLE CONTEXT)
# =================================================
def build_equity_snapshot_warnings(trade: Trade) -> Optional[List[Dict[str, Any]]]:
    if trade.account_equity_at_entry is None or trade.account_equity_at_entry <= 0:
        return None

    results: List[Dict[str, Any]] = []

    # -------------------------------------------------
    # RULE: Exposure without stop loss (fallback rule)
    # -------------------------------------------------
    if trade.stop_loss is None:
        notional = trade.entry_price * trade.original_quantity
        exposure_pct = float(notional / trade.account_equity_at_entry)

        if exposure_pct >= 0.10:
            results.append(
                {
                    "code": EXPOSURE_NO_STOP,
                    "severity": "critical" if exposure_pct >= 0.25 else "warning",
                    "metric": "exposure_pct",
                    "allowed": 0.10,
                    "actual": round(exposure_pct, 4),
                    "message": (
                        f"{exposure_pct:.2%} of account committed "
                        "without a stop loss"
                    ),
                    "engine": ENGINE_EQUITY_SNAPSHOT,
                    "resolved": False,
                }
            )

    # -------------------------------------------------
    # RULE: Stop-based risk % of account
    # -------------------------------------------------
    if trade.stop_loss is not None and trade.risk_pct_at_entry is not None:
        risk_pct = float(trade.risk_pct_at_entry)

        if risk_pct >= 0.02:
            results.append(
                {
                    "code": MAX_RISK_PCT,
                    "severity": "critical" if risk_pct >= 0.05 else "warning",
                    "metric": "risk_pct",
                    "allowed": 0.02,
                    "actual": round(risk_pct, 4),
                    "message": f"Risk per trade is {risk_pct:.2%} of account",
                    "engine": ENGINE_EQUITY_SNAPSHOT,
                    "resolved": False,
                }
            )

    return results or None


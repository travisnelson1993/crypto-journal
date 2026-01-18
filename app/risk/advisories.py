from typing import Optional, Dict, Any
from app.models.trade import Trade


# =================================================
# CORE ADVISORY ENGINE (CANONICAL ENTRYPOINT)
# =================================================
def compute_risk_advisories(trade: Trade) -> Optional[Dict[str, Any]]:
    warnings: Dict[str, Any] = {}

    stop_based = build_stop_based_risk_warning(trade)
    if stop_based:
        warnings.update(stop_based)

    exposure_based = build_exposure_based_warning(trade)
    if exposure_based:
        warnings.update(exposure_based)

    return warnings or None


# =================================================
# PRIMARY RULE — Stop-based risk % of account
# =================================================
def build_stop_based_risk_warning(trade: Trade) -> Optional[Dict[str, Any]]:
    if (
        trade.account_equity_at_entry is None
        or trade.account_equity_at_entry <= 0
        or trade.stop_loss is None
        or trade.risk_pct_at_entry is None
    ):
        return None

    risk_pct = float(trade.risk_pct_at_entry)

    if risk_pct < 0.02:
        return None

    return {
        "RISK_PCT_HIGH": {
            "severity": "critical" if risk_pct >= 0.05 else "warning",
            "rule": "max_risk_pct",
            "allowed_pct": 0.02,
            "actual_pct": round(risk_pct, 4),
            "message": f"Risk per trade is {risk_pct:.2%} of account",
        }
    }


# =================================================
# FALLBACK RULE — Exposure % (ONLY if no stop)
# =================================================
def build_exposure_based_warning(trade: Trade) -> Optional[Dict[str, Any]]:
    if (
        trade.account_equity_at_entry is None
        or trade.account_equity_at_entry <= 0
        or trade.stop_loss is not None
    ):
        return None

    notional = trade.entry_price * trade.original_quantity
    exposure_pct = float(notional / trade.account_equity_at_entry)

    if exposure_pct < 0.10:
        return None

    return {
        "EXPOSURE_HIGH": {
            "severity": "critical" if exposure_pct >= 0.25 else "warning",
            "rule": "max_exposure_pct",
            "allowed_pct": 0.10,
            "actual_pct": round(exposure_pct, 4),
            "message": f"{exposure_pct:.2%} of account committed without a stop loss",
        }
    }


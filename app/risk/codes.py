# app/risk/codes.py

EXPOSURE_NO_STOP = "EXPOSURE_NO_STOP"
MAX_RISK_PCT = "MAX_RISK_PCT"

RISK_CODES = {
    EXPOSURE_NO_STOP: {
        "category": "exposure",
        "default_severity": "critical",
        "description": "Exposure exceeds safe threshold without stop loss",
    },
    MAX_RISK_PCT: {
        "category": "risk",
        "default_severity": "warning",
        "description": "Risk per trade exceeds allowed percent",
    },
}


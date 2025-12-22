import re
from typing import Literal, Optional, Tuple

_ws_re = re.compile(r"\s+", flags=re.UNICODE)

def _normalize_text(s: Optional[str]) -> str:
    if s is None:
        return ""

    # Replace common odd whitespace + dashes
    s = s.replace("\u00A0", " ")   # NBSP
    s = s.replace("\u200B", "")   # zero-width space
    s = s.replace("\u200C", "")   # zero-width non-joiner
    s = s.replace("\u200D", "")   # zero-width joiner
    s = s.replace("—", "-").replace("–", "-")

    # Strip non-printing control chars (keep normal unicode letters)
    s = "".join(ch for ch in s if ch.isprintable())

    s = s.strip()
    s = _ws_re.sub(" ", s)
    return s

_re_open  = re.compile(r"\bopen\b", re.I)
_re_close = re.compile(r"\bclose\b", re.I)
_re_long  = re.compile(r"\blong\b", re.I)
_re_short = re.compile(r"\bshort\b", re.I)

_re_tp = re.compile(r"\b(tp|take profit|take-profit)\b", re.I)
_re_sl = re.compile(r"\b(sl|stop loss|stop-loss|stop)\b", re.I)

def infer_action_and_direction(
    side: Optional[str],
) -> Tuple[Optional[Literal["OPEN", "CLOSE"]], Optional[Literal["LONG", "SHORT"]], Optional[str]]:
    s = _normalize_text(side)
    if not s:
        return None, None, None

    action: Optional[Literal["OPEN","CLOSE"]] = None
    if _re_open.search(s):
        action = "OPEN"
    elif _re_close.search(s):
        action = "CLOSE"

    direction: Optional[Literal["LONG","SHORT"]] = None
    if _re_long.search(s):
        direction = "LONG"
    elif _re_short.search(s):
        direction = "SHORT"

    reason = "TP" if _re_tp.search(s) else ("SL" if _re_sl.search(s) else None)
    return action, direction, reason

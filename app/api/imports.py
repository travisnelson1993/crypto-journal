import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.trade import Trade

# Define router with a safe, unique endpoint prefix
router = APIRouter(prefix="/api/import", tags=["imports"])


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


_qty_re = re.compile(r"([+-]?[0-9,]*\.?[0-9]+)")


def parse_money(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    v = value.strip()
    if v in ("", "--", "-"):
        return None
    v = v.replace("%", "").strip()
    v = re.sub(r"[A-Za-z]+$", "", v).strip()
    v = v.replace(",", "")
    if v.startswith("(") and v.endswith(")"):
        v = "-" + v[1:-1]
    try:
        return float(v)
    except Exception:
        m = _qty_re.search(v)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None
        return None


def parse_qty_unit(filled: Optional[str]):
    if not filled:
        return None, None
    s = filled.strip()
    parts = s.split()
    if len(parts) >= 2:
        try:
            qty = float(parts[0].replace(",", ""))
            unit = parts[1]
            return qty, unit
        except Exception:
            m = _qty_re.search(s)
            if m:
                try:
                    return float(m.group(1)), (parts[-1] if len(parts) > 1 else None)
                except Exception:
                    return None, None
    else:
        m = _qty_re.search(s)
        if m:
            try:
                return float(m.group(1)), None
            except Exception:
                return None, None
    return None, None


def parse_datetime(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    fmts = ["%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            continue
    try:
        from dateutil.parser import parse as dateutil_parse

        return dateutil_parse(s)
    except Exception:
        return None


def heuristic_from_side(side_raw: Optional[str]):
    """Detect action/direction heuristically via side_raw value."""
    if not side_raw:
        return None, None, None
    s = str(side_raw).strip()
    lower = s.lower()
    action = None
    direction = None
    reason = None

    if "open" in lower:
        action = "OPEN"
    elif "close" in lower:
        action = "CLOSE"

    if "short" in lower:
        direction = "SHORT"
    elif "long" in lower:
        direction = "LONG"

    if "tp" in lower or "take profit" in lower:
        reason = "TP"
    elif "sl" in lower or "stop" in lower:
        reason = "SL"

    return action, direction, reason


@router.post("/csv", status_code=status.HTTP_200_OK)
async def import_csv(
    file: UploadFile = File(...),
    mode: str = Query("append", regex="^(append|replace)$"),
    session: AsyncSession = Depends(get_session),
):
    """Import a CSV file containing trades."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty CSV")

    text = contents.decode(errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    if mode == "replace":
        await session.execute(delete(Trade))
        await session.commit()

    normalized_rows: List[Dict[str, Any]] = []
    skipped_rows = 0
    skipped_examples: List[Dict[str, Any]] = []
    created_trades = 0
    closed_trades = 0
    orphan_closes_created = 0
    _merged_orphans = 0

    # Normalize rows
    for raw in reader:
        side_raw = raw.get("Side") or raw.get("side") or ""
        action, direction, close_reason = heuristic_from_side(side_raw)
        symbol = (
            raw.get("Underlying Asset") or raw.get("Ticker") or raw.get("symbol") or ""
        ).strip()
        order_time = parse_datetime(raw.get("Order Time") or raw.get("Order Date"))
        avg_fill = parse_money(raw.get("Avg Fill"))
        filled_qty, filled_unit = parse_qty_unit(raw.get("Filled"))

        if not action or not direction or not symbol:
            skipped_rows += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "missing_data", "row": raw})
            continue

        normalized_rows.append(
            {
                "raw": raw,
                "symbol": symbol,
                "order_time": order_time,
                "action": action,
                "direction": direction,
                "close_reason": close_reason,
                "avg_fill": avg_fill,
                "filled_qty": filled_qty,
            }
        )

    # Execute trades
    for nr in normalized_rows:
        action = nr["action"]
        direction = nr["direction"]
        symbol = nr["symbol"]
        entry_date = nr["order_time"]
        avg_fill = nr["avg_fill"]
        close_reason = nr["close_reason"]

        if action == "OPEN":
            trade = Trade(
                ticker=symbol,
                direction=direction,
                entry_price=avg_fill,
                leverage=None,  # Set default leverage or map if available
                entry_date=entry_date or datetime.utcnow(),
                source="blofin_order_history",
            )
            session.add(trade)
            created_trades += 1
        elif action == "CLOSE":
            query = select(Trade).where(
                Trade.ticker == symbol,
                Trade.direction == direction,
                Trade.end_date.is_(None),
            )
            result = await session.execute(query)
            open_trade = result.scalars().first()
            if open_trade:
                open_trade.exit_price = avg_fill
                open_trade.end_date = entry_date
                closed_trades += 1
                session.add(open_trade)
            else:
                orphan_close = Trade(
                    ticker=symbol,
                    direction=direction,
                    entry_price=avg_fill,
                    exit_price=avg_fill,
                    end_date=entry_date or datetime.utcnow(),
                    entry_date=entry_date or datetime.utcnow(),
                    orphan_close=True,
                    source="blofin_order_history",
                )
                session.add(orphan_close)
                orphan_closes_created += 1

    await session.commit()
    return {
        "ok": True,
        "source": "blofin_order_history",
        "created_trades": created_trades,
        "closed_trades": closed_trades,
        "orphan_closes_created": orphan_closes_created,
        "skipped_rows": skipped_rows,
        "skipped_examples": skipped_examples,
    }

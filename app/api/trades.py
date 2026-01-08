import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_sessionmaker
from app.models.trade import Trade

# Router
router = APIRouter(prefix="/api/import", tags=["imports"])

# ---------------- DB dependency (ASYNC) ----------------

async def get_db():
    SessionLocal = get_async_sessionmaker()
    async with SessionLocal() as session:
        yield session


# ---------------- helpers ----------------

_qty_re = re.compile(r"([+-]?[0-9,]*\.?[0-9]+)")


def parse_money(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    v = str(value).strip()
    if v in ("", "--", "-"):
        return None

    v = v.replace("%", "").strip()
    v = re.sub(r"[A-Za-z]+$", "", v).strip()  # remove trailing units like "USDT"
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


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    return None


def heuristic_from_side(side: Optional[str]):
    if not side:
        return None, None, None
    s = str(side).strip().lower()

    action = None
    if s.startswith("open") or " open" in s:
        action = "OPEN"
    elif s.startswith("close") or " close" in s:
        action = "CLOSE"

    direction = None
    if "long" in s:
        direction = "LONG"
    elif "short" in s:
        direction = "SHORT"

    reason = None
    if "tp" in s or "take profit" in s:
        reason = "TP"
    elif "sl" in s or "stop" in s:
        reason = "SL"

    return action, direction, reason


# ---------------- endpoint ----------------

@router.post("/csv", status_code=status.HTTP_200_OK)
async def import_csv(
    file: UploadFile = File(...),
    mode: str = Query("append", pattern="^(append|replace)$"),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty CSV")

    reader = csv.DictReader(io.StringIO(contents.decode(errors="replace")))

    if mode == "replace":
        await db.execute(delete(Trade))
        await db.commit()

    created = 0
    closed = 0
    orphan = 0
    skipped = 0
    skipped_examples: List[Dict[str, Any]] = []

    for raw in reader:
        action, direction, _ = heuristic_from_side(raw.get("Side") or raw.get("side"))
        symbol = (
            raw.get("Underlying Asset")
            or raw.get("Ticker")
            or raw.get("symbol")
            or ""
        ).strip()

        if not action or not direction or not symbol:
            skipped += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "missing action/direction/symbol", "row": raw})
            continue

        entry_date = parse_datetime(raw.get("Order Time") or raw.get("Order Date"))
        price = parse_money(raw.get("Avg Fill"))

        if price is None:
            skipped += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "missing/invalid Avg Fill", "row": raw})
            continue

        if action == "OPEN":
            db.add(
                Trade(
                    ticker=symbol,
                    direction=direction,
                    entry_price=price,
                    entry_date=entry_date or datetime.utcnow(),
                    source="blofin_order_history",
                )
            )
            created += 1

        else:  # CLOSE
            result = await db.execute(
                select(Trade)
                .where(
                    Trade.ticker == symbol,
                    Trade.direction == direction,
                    Trade.end_date.is_(None),
                )
                .order_by(Trade.entry_date.desc())
                .limit(1)
            )
            open_trade = result.scalars().first()

            if open_trade:
                open_trade.exit_price = price
                open_trade.end_date = entry_date or datetime.utcnow()
                closed += 1
            else:
                db.add(
                    Trade(
                        ticker=symbol,
                        direction=direction,
                        entry_price=price,
                        exit_price=price,
                        entry_date=entry_date or datetime.utcnow(),
                        end_date=entry_date or datetime.utcnow(),
                        orphan_close=True,
                        source="blofin_order_history",
                    )
                )
                orphan += 1

    await db.commit()

    return {
        "ok": True,
        "created_trades": created,
        "closed_trades": closed,
        "orphan_closes_created": orphan,
        "skipped_rows": skipped,
        "skipped_examples": skipped_examples,
    }

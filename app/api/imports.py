import csv
import io
import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

# -------------------------------------------------
# Router
# -------------------------------------------------
router = APIRouter(prefix="/api/import", tags=["imports"])

# -------------------------------------------------
# Helpers
# -------------------------------------------------
_qty_re = re.compile(r"([+-]?[0-9,]*\.?[0-9]+)")


def parse_money(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None

    v = str(value).strip().replace(",", "")
    if v in ("", "--", "-"):
        return None

    try:
        return Decimal(v)
    except Exception:
        m = _qty_re.search(v)
        return Decimal(m.group(1)) if m else None


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    value = value.strip()
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass

    return None


def parse_side(side: Optional[str]):
    """
    Blofin Side examples:
    - Open Long
    - Close Long(SL)
    - Open Short
    - Close Short(TP)
    """
    if not side:
        return None, None

    s = side.lower()
    s = re.sub(r"\(.*?\)", "", s).strip()

    if s.startswith("open long"):
        return "OPEN", "long"
    if s.startswith("close long"):
        return "CLOSE", "long"
    if s.startswith("open short"):
        return "OPEN", "short"
    if s.startswith("close short"):
        return "CLOSE", "short"

    return None, None


# -------------------------------------------------
# CSV IMPORT (EXECUTION-ONLY LEDGER)
# -------------------------------------------------
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

    rows = list(csv.DictReader(io.StringIO(contents.decode(errors="replace"))))

    # Sort by execution time (critical for later derivations)
    rows.sort(
        key=lambda r: parse_datetime(r.get("Order Time") or r.get("Order Date"))
        or datetime.min
    )

    if mode == "replace":
        # Safe in test DB — rebuilds everything deterministically
        await db.execute("DELETE FROM trades")
        await db.commit()

    created = skipped = 0

    for raw in rows:
        action, direction = parse_side(raw.get("Side"))

        symbol = (
            raw.get("Underlying Asset")
            or raw.get("Ticker")
            or raw.get("Symbol")
            or raw.get("symbol")
            or ""
        ).strip().upper()

        if not action or not direction or not symbol:
            skipped += 1
            continue

        price = parse_money(raw.get("Avg Fill"))
        qty = parse_money(raw.get("Filled"))
        leverage = parse_money(raw.get("Leverage")) or Decimal("1")
        fee = parse_money(raw.get("Fee")) or Decimal("0")
        ts = parse_datetime(raw.get("Order Time") or raw.get("Order Date"))

        if price is None or qty is None or qty <= 0:
            skipped += 1
            continue

        # -------------------------------------------------
        # EXECUTION-LEVEL TRADE ROW
        # -------------------------------------------------
        trade = Trade(
            ticker=symbol,
            direction=direction,
            quantity=qty,
            original_quantity=qty,
            leverage=leverage,
            fee=fee,
            source="blofin_order_history",
        )

        if action == "OPEN":
            trade.entry_price = price
            trade.entry_date = ts
            trade.exit_price = None
            trade.end_date = None

        else:  # CLOSE
            trade.entry_price = None
            trade.entry_date = None
            trade.exit_price = price
            trade.end_date = ts
            trade.quantity = Decimal("0")

        db.add(trade)
        created += 1

    await db.commit()

    return {
        "ok": True,
        "created_trades": created,
        "skipped_rows": skipped,
    }

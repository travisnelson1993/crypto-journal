import csv
import io
import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.executions import Execution

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
        return "OPEN", "LONG"
    if s.startswith("close long"):
        return "CLOSE", "LONG"
    if s.startswith("open short"):
        return "OPEN", "SHORT"
    if s.startswith("close short"):
        return "CLOSE", "SHORT"

    return None, None


# -------------------------------------------------
# CSV IMPORT (EXECUTION-ONLY LEDGER — v2 LOCKED)
# -------------------------------------------------
@router.post("/csv", status_code=status.HTTP_200_OK)
async def import_csv_v2(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty CSV")

    rows = list(csv.DictReader(io.StringIO(contents.decode(errors="replace"))))

    rows.sort(
        key=lambda r: parse_datetime(r.get("Order Time") or r.get("Order Date"))
        or datetime.min
    )

    created = skipped = duplicates = 0

    async with db.begin():  # ✅ ONE outer transaction
        for raw in rows:
            side, direction = parse_side(raw.get("Side"))

            symbol = (
                raw.get("Underlying Asset")
                or raw.get("Ticker")
                or raw.get("Symbol")
                or ""
            ).strip().upper()

            if not side or not direction or not symbol:
                skipped += 1
                continue

            price = parse_money(raw.get("Avg Fill"))
            qty = parse_money(raw.get("Filled"))
            fee = parse_money(raw.get("Fee")) or Decimal("0")
            ts = parse_datetime(raw.get("Order Time") or raw.get("Order Date"))

            if price is None or qty is None or qty <= 0 or ts is None:
                skipped += 1
                continue

            execution = Execution(
                source="blofin",
                source_filename=file.filename,
                ticker=symbol,
                side=side,
                direction=direction,
                price=price,
                quantity=qty,
                remaining_qty=qty if side == "OPEN" else Decimal("0"),
                timestamp=ts,
                fee=fee,
            )

            # 🔐 SAVEPOINT per execution
            async with db.begin_nested():
                try:
                    db.add(execution)
                    await db.flush()
                    created += 1
                except IntegrityError:
                    duplicates += 1
                    # nested transaction auto-rolls back
                    continue

    return {
        "ok": True,
        "created_executions": created,
        "duplicate_executions": duplicates,
        "skipped_rows": skipped,
    }

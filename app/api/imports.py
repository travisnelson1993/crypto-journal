import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.database import AsyncSessionLocal
from app.models.trade import Trade

# Router
router = APIRouter(prefix="/api/import", tags=["imports"])


# ---------------- DB dependency (SYNC) ----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- helpers ----------------

_qty_re = re.compile(r"([+-]?[0-9,]*\.?[0-9]+)")


def parse_money(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    v = value.strip().replace(",", "").replace("%", "")
    if v in ("", "--", "-"):
        return None
    if v.startswith("(") and v.endswith(")"):
        v = "-" + v[1:-1]
    try:
        return float(v)
    except Exception:
        m = _qty_re.search(v)
        return float(m.group(1)) if m else None


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except Exception:
            pass
    return None


def heuristic_from_side(side: Optional[str]):
    if not side:
        return None, None, None
    s = side.lower()
    action = "OPEN" if "open" in s else "CLOSE" if "close" in s else None
    direction = "LONG" if "long" in s else "SHORT" if "short" in s else None
    reason = "TP" if "tp" in s else "SL" if "sl" in s else None
    return action, direction, reason


# ---------------- endpoint ----------------

@router.post("/csv", status_code=status.HTTP_200_OK)
def import_csv(
    file: UploadFile = File(...),
    mode: str = Query("append", pattern="^(append|replace)$"),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file")

    contents = file.file.read()
    if not contents:
        raise HTTPException(400, "Empty CSV")

    reader = csv.DictReader(io.StringIO(contents.decode(errors="replace")))

    if mode == "replace":
        db.execute(delete(Trade))
        db.commit()

    created = closed = orphan = skipped = 0
    skipped_examples: List[Dict[str, Any]] = []

    for raw in reader:
        action, direction, _ = heuristic_from_side(raw.get("Side"))
        symbol = (
            raw.get("Underlying Asset")
            or raw.get("Ticker")
            or raw.get("symbol")
            or ""
        ).strip()

        if not action or not direction or not symbol:
            skipped += 1
            if len(skipped_examples) < 5:
                skipped_examples.append(raw)
            continue

        entry_date = parse_datetime(raw.get("Order Time"))
        price = parse_money(raw.get("Avg Fill"))

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
            open_trade = (
                db.execute(
                    select(Trade)
                    .where(
                        Trade.ticker == symbol,
                        Trade.direction == direction,
                        Trade.end_date.is_(None),
                    )
                    .order_by(Trade.entry_date.desc())
                )
                .scalars()
                .first()
            )

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

    db.commit()

    return {
        "ok": True,
        "created_trades": created,
        "closed_trades": closed,
        "orphan_closes_created": orphan,
        "skipped_rows": skipped,
        "skipped_examples": skipped_examples,
    }

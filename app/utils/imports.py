from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Query
import csv
import io
import re
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.trade import Trade
from app.utils.side_parser import infer_action_and_direction

router = APIRouter(prefix="/api/trades/import", tags=["imports"])


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


_qty_re = re.compile(r'([+-]?[0-9,]*\.?[0-9]+)')


def parse_money(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    v = value.strip()
    if v == "" or v in ("--", "-"):
        return None

    v = v.replace("%", "").strip()
    v = v.replace(",", "")

    # Remove trailing currency/token letters (e.g., "86855.7 USDT")
    # Keep only the first numeric portion.
    m = _qty_re.search(v)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None


def parse_qty_unit(filled: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    if not filled:
        return None, None
    s = filled.strip()
    parts = s.split()
    if len(parts) >= 2:
        try:
            return float(parts[0].replace(",", "")), parts[1]
        except Exception:
            pass
    m = _qty_re.search(s)
    if m:
        try:
            return float(m.group(1).replace(",", "")), (parts[-1] if len(parts) > 1 else None)
        except Exception:
            return None, None
    return None, None


def parse_datetime_utc(s: Optional[str]) -> Optional[datetime]:
    """Parse common exchange timestamps and return timezone-aware UTC datetime."""
    if not s:
        return None
    s = s.strip()

    fmts = [
        "%m/%d/%Y %H:%M:%S",          # Blofin example: 12/12/2025 16:19:06
        "%Y-%m-%dT%H:%M:%S",          # ISO without Z
        "%Y-%m-%dT%H:%M:%S.%f",       # ISO with ms
        "%m/%d/%Y",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    # dateutil fallback if installed
    try:
        from dateutil.parser import parse as dateutil_parse
        dt = dateutil_parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_leverage(value: Optional[str]) -> float:
    """Always return a float leverage; default to 1.0 if missing/invalid."""
    if value is None:
        return 1.0
    v = str(value).strip()
    if v == "" or v == "--":
        return 1.0
    try:
        return float(v.replace("x", "").replace("X", ""))
    except Exception:
        return 1.0


@router.post("/csv", status_code=status.HTTP_200_OK)
async def import_csv(
    file: UploadFile = File(...),
    mode: str = Query("append", pattern="^(append|replace)$"),
    session: AsyncSession = Depends(get_session),
):
    """
    Import an exchange CSV (Blofin-style).

    Behavior:
    - OPEN rows create an open Trade (exit_price/end_date remain null)
    - CLOSE rows try to close the most recent matching open Trade (same ticker+direction with end_date is null)
    - If no open is found, create an orphan_close Trade (entry_date set to close time to satisfy NOT NULL)
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty CSV")

    # Replace mode (dev only)
    if mode == "replace":
        await session.execute(text("DELETE FROM trades;"))
        await session.commit()

    text_data = contents.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))

    skipped_rows = 0
    skipped_examples: List[Dict[str, Any]] = []
    created_trades = 0
    closed_trades = 0
    orphan_closes_created = 0

    # Normalize rows first, then sort by time (so we process in order)
    rows: List[Dict[str, Any]] = []
    for raw in reader:
        side_raw = (raw.get("Side") or raw.get("side") or "").strip()
        action, direction, close_reason = infer_action_and_direction(side_raw)

        ticker = (
            raw.get("Underlying Asset")
            or raw.get("Ticker")
            or raw.get("ticker")
            or raw.get("symbol")
            or ""
        ).strip()

        order_time = parse_datetime_utc(raw.get("Order Time") or raw.get("Order Date") or raw.get("Time"))
        avg_fill = parse_money(raw.get("Avg Fill"))
        price = parse_money(raw.get("Price"))
        filled_qty, filled_unit = parse_qty_unit(raw.get("Filled"))
        pnl = parse_money(raw.get("PNL"))
        pnl_pct = parse_money(raw.get("PNL%"))
        fee = parse_money(raw.get("Fee"))
        leverage = parse_leverage(raw.get("Leverage"))

        # Must at least have ticker + side action/direction + timestamp + a usable price
        px = avg_fill if avg_fill is not None else price

        if not ticker:
            skipped_rows += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "missing ticker", "row": raw})
            continue

        rows.append(
            {
                "raw": raw,
                "ticker": ticker,
                "side_raw": side_raw,
                "action": action,
                "direction": direction,
                "close_reason": close_reason,
                "order_time": order_time,
                "price": px,
                "leverage": leverage,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "fee": fee,
                "filled_qty": filled_qty,
                "filled_unit": filled_unit,
            }
        )

    rows.sort(key=lambda r: (r["order_time"] is None, r["order_time"]))

    async def find_open_trade(ticker: str, direction: str) -> Optional[Trade]:
        q = (
            select(Trade)
            .where(
                Trade.ticker == ticker,
                Trade.direction == direction,
                Trade.end_date.is_(None),
            )
            .order_by(Trade.entry_date.desc())  # LIFO is usually best for exchange fills
            .limit(1)
        )
        res = await session.execute(q)
        return res.scalars().first()

    # Process
    for r in rows:
        action = r["action"]
        direction = r["direction"]
        ticker = r["ticker"]
        dt = r["order_time"]
        px = r["price"]
        lev = r["leverage"]

        if not action or not direction:
            skipped_rows += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "could not infer action/direction", "row": r["raw"]})
            continue

        if dt is None:
            skipped_rows += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "missing/invalid order_time", "row": r["raw"]})
            continue

        if px is None:
            skipped_rows += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": "missing/invalid price (Avg Fill/Price)", "row": r["raw"]})
            continue

        action = action.upper()
        direction = direction.upper()

        if action == "OPEN":
            t = Trade(
                ticker=ticker,
                direction=direction,
                entry_price=px,
                exit_price=None,
                stop_loss=None,
                leverage=lev,
                entry_date=dt,
                end_date=None,
                entry_summary=f"Imported (open): {r['side_raw']}",
                orphan_close=False,
                source="blofin_order_history",
            )
            session.add(t)
            created_trades += 1

        elif action == "CLOSE":
            open_trade = await find_open_trade(ticker, direction)

            if open_trade:
                open_trade.exit_price = px
                open_trade.end_date = dt
                # keep orphan_close False
                closed_trades += 1
            else:
                # Orphan close: entry_date must NOT be null per DB schema
                orphan = Trade(
                    ticker=ticker,
                    direction=direction,
                    entry_price=px,   # placeholder so required field is satisfied
                    exit_price=px,
                    stop_loss=None,
                    leverage=lev,
                    entry_date=dt,    # set to close time to satisfy NOT NULL
                    end_date=dt,
                    entry_summary=f"Imported (orphan close): {r['side_raw']}",
                    orphan_close=True,
                    source="blofin_order_history",
                )
                session.add(orphan)
                orphan_closes_created += 1
                closed_trades += 1

        else:
            skipped_rows += 1
            if len(skipped_examples) < 5:
                skipped_examples.append({"reason": f"unknown action {action}", "row": r["raw"]})
            continue

    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"DB commit failed: {exc}")

    return {
        "ok": True,
        "source": "blofin_order_history",
        "created_trades": created_trades,
        "closed_trades": closed_trades,
        "orphan_closes_created": orphan_closes_created,
        "merged_orphans": 0,
        "skipped_rows": skipped_rows,
        "skipped_examples": skipped_examples[:10],
        "note": "Close rows match the most recent open trade (same ticker+direction). Orphan closes are saved with orphan_close=True.",
    }

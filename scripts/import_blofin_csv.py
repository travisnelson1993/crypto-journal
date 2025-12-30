# CSV importer that inserts executions and triggers matching
# Adjust import path to your project's session creation
import csv
import hashlib
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import os

from app.db import SessionLocal
from app.services.matcher import insert_execution_and_match

def row_hash(source: str, filename: str, row: dict) -> str:
    # Create a deterministic row hash for idempotency
    payload = f"{source}|{filename}|{'|'.join([f'{k}={row[k]}' for k in sorted(row.keys())])}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def parse_filled_field(filled: str):
    """
    Parse the 'Filled' field like '0.123 BTC' or '100 ETH' -> return (qty_decimal, ticker)
    Accepts a few variants (qty first or ticker first).
    """
    if not filled:
        return None, None
    s = filled.strip()
    # common patterns: "0.123 BTC", "BTC 0.123", "0.123BTC"
    parts = s.replace(',', '').split()
    # qty + ticker
    if len(parts) >= 2:
        # try qty first
        try:
            qty = Decimal(parts[0])
            ticker = parts[1].upper()
            return qty, ticker
        except InvalidOperation:
            pass
        # try ticker first
        try:
            qty = Decimal(parts[-1])
            ticker = parts[0].upper()
            return qty, ticker
        except InvalidOperation:
            pass
    # try extracting trailing number
    import re
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)', s)
    if m:
        try:
            qty = Decimal(m.group(1))
            # guess ticker as non-number part
            ticker = re.sub(r'[0-9\.\s,]+', '', s).upper()
            ticker = ticker or None
            return qty, ticker
        except InvalidOperation:
            return None, None
    return None, None

def _map_side_and_direction(side_raw: str):
    s = (side_raw or '').strip().lower()
    side = 'OPEN' if 'open' in s else ('CLOSE' if 'close' in s else 'OPEN')
    direction = 'LONG' if 'long' in s else ('SHORT' if 'short' in s else 'LONG')
    return side, direction

def _safe_decimal(s):
    if s is None or s == '':
        return None
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError, TypeError):
        return None

def import_csv(path: str, source: str = 'blofin', source_filename: str = None):
    """
    Import CSV rows into executions. Supports multiple CSV formats:
    - Rows with 'Filled' column like "0.123 BTC" (qty + ticker).
    - Fallback: rows with 'Underlying Asset' and 'Avg Fill' (no qty column) — quantity defaults to 1.
    """
    source_filename = source_filename or os.path.basename(path)
    with open(path, newline='') as fh:
        reader = csv.DictReader(fh)
        with SessionLocal() as db:
            for row in reader:
                # Try the Filled field first (various capitalizations)
                filled_field = row.get('Filled') or row.get('filled') or row.get('filled_amount') or row.get('Amount')
                qty, ticker = parse_filled_field(filled_field) if filled_field else (None, None)

                price = _safe_decimal(row.get('Price') or row.get('price') or row.get('Avg Fill') or row.get('AvgFill'))
                # If Filled parsing didn't yield qty/ticker, try the Underlying Asset fallback
                if (qty is None or ticker is None) and row.get('Underlying Asset'):
                    raw_asset = row.get('Underlying Asset').strip()
                    # preserve the asset string (e.g., BTCUSDT). If you prefer JUST base (BTC), you can strip the quote suffix.
                    ticker = raw_asset.upper()
                    # quantity: try common names, otherwise default to 1
                    qty = _safe_decimal(row.get('Quantity') or row.get('Qty') or row.get('Amount') or row.get('Size'))
                    if qty is None:
                        qty = Decimal('1')

                if not qty or not ticker:
                    # still couldn't parse a qty+ticker; skip this row
                    continue

                side_raw = row.get('Side') or row.get('side') or ''
                side, direction = _map_side_and_direction(side_raw)

                payload = {
                    'source': source,
                    'source_filename': source_filename,
                    'source_rowhash': row_hash(source, source_filename, row),
                    'source_execution_id': row.get('id') or row.get('execution_id'),
                    'ticker': ticker,
                    'direction': direction,
                    'side': side,
                    'quantity': abs(qty),
                    'price': price,
                    'fee': _safe_decimal(row.get('Fee') or row.get('fee')),
                    'occurred_at': None
                }

                # Try parse timestamp columns if present
                ts = row.get('Order Time') or row.get('Timestamp') or row.get('timestamp') or row.get('Time')
                if ts:
                    try:
                        # try common formats; tests can provide timezone-naive strings
                        payload['occurred_at'] = datetime.fromisoformat(ts)
                    except Exception:
                        try:
                            # common US-style format from fixture: 12/16/2025 12:17:29
                            payload['occurred_at'] = datetime.strptime(ts, "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
                        except Exception:
                            payload['occurred_at'] = None

                insert_execution_and_match(db, payload)

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python import_blofin_csv.py path/to/file.csv")
        sys.exit(2)
    import_csv(sys.argv[1])

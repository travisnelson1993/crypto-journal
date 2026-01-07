#!/usr/bin/env python3
"""
Import Blofin CSV(s) into the trades table.

CI-SAFE / TRANSACTION-SAFE
--------------------------
- NO ON CONFLICT
- NO SAVEPOINTS
- Each CSV row is executed in its own transaction (commit/rollback per row)
  so a single bad row cannot poison the whole import.
- Uses WHERE NOT EXISTS for open-trade idempotency (works even if the
  uniq_open_trade_on_fields index is missing).
- Close rows are always inserted (so total rows == CSV rows).
- Records imported_files by SHA-256 (skips exact file re-imports).

Usage examples:
  python import_blofin_csv.py --input "/path/to/Order_history_*.csv" --db "$CRYPTO_JOURNAL_DSN"
  python import_blofin_csv.py --input "/path/to/csv_dir" --archive-dir "/path/to/archive" --tz "America/Los_Angeles" --db "$CRYPTO_JOURNAL_DSN"
"""

import argparse
import glob
import hashlib
import os
import shutil
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2

from app.utils.side_parser import infer_action_and_direction

SOURCE_NAME = "blofin_order_history"


# ---------------- helpers ----------------

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_price(s):
    if s is None:
        return None
    if not isinstance(s, str):
        try:
            return float(s)
        except Exception:
            return None

    s = s.strip()
    if s in ("", "--", "Market"):
        return None

    # Accept values like "123.45", "123.45 USDT", "1e-6", etc.
    import re
    m = re.match(r"([0-9\.\-eE]+)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def parse_datetime(s, tz=None):
    try:
        dt = pd.to_datetime(s, format="%m/%d/%Y %H:%M:%S", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return None

        ts = dt.to_pydatetime()
        if tz:
            local = ts.replace(tzinfo=ZoneInfo(tz))
            return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return ts
    except Exception:
        return None


def make_entry_summary(side, status):
    side = side or ""
    status = status or ""
    side_norm = side.lower()

    if side_norm.startswith("open"):
        return f"Imported: {side}"

    # Keep your original intent here
    if status.lower().startswith("filled"):
        return f"Imported orphan close: {side}"

    return f"Imported close: {side}"


def ensure_imported_files_table(conn):
    # DDL should be outside a long-running transaction; use autocommit.
    # In CI this prevents "current transaction is aborted" cascades.
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS imported_files (
              id SERIAL PRIMARY KEY,
              filename TEXT NOT NULL,
              file_hash TEXT NOT NULL UNIQUE,
              imported_at TIMESTAMP DEFAULT now()
            );
            """
        )


def find_open_trade_and_update(cur, ticker, direction, close_price, close_dt, entry_price=None, price_tolerance=0.0001):
    """
    Best-effort: update an existing open trade (exit_price IS NULL) with close data.
    Does NOT overwrite source_filename/created_at.
    Returns True if an update occurred, False otherwise.
    """
    cur.execute(
        """
        SELECT id, entry_price, entry_date
        FROM trades
        WHERE ticker = %s
          AND direction = %s
          AND exit_price IS NULL
          AND entry_date <= %s
        ORDER BY entry_date DESC, created_at DESC
        LIMIT 1
        """,
        (ticker, direction, close_dt),
    )
    row = cur.fetchone()
    if not row:
        return False

    trade_id, existing_entry_price, _existing_entry_date = row

    # Optional price check (non-blocking)
    if entry_price is not None:
        try:
            if abs(float(existing_entry_price) - float(entry_price)) > price_tolerance:
                pass
        except Exception:
            pass

    cur.execute(
        """
        UPDATE trades
        SET exit_price = %s,
            end_date = %s,
            entry_summary = COALESCE(entry_summary, %s),
            orphan_close = %s,
            is_duplicate = %s
        WHERE id = %s
        """,
        (close_price, close_dt, f"Imported: Close @ {close_price}", False, False, trade_id),
    )
    return cur.rowcount > 0


# ---------------- core ----------------

def process_file(conn, file_path, tz=None, archive_dir=None, dry_run=False):
    print(f"Processing: {file_path}")
    basename = os.path.basename(file_path)
    file_hash = file_sha256(file_path)

    # Ensure imported_files exists (DDL)
    # Use a separate short autocommit block so it can't poison the main flow
    prev_autocommit = conn.autocommit
    try:
        conn.autocommit = True
        ensure_imported_files_table(conn)
    finally:
        conn.autocommit = prev_autocommit

    # Skip if already imported (hash match)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM imported_files WHERE file_hash = %s", (file_hash,))
        if cur.fetchone():
            print("  -> already imported (hash match). Skipping.")
            return

    df = pd.read_csv(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Track how many rows we actually inserted (helpful for CI logs)
    inserted_rows = 0
    failed_rows = 0

    for i, row in df.iterrows():
        # Build the record
        ticker = (
            (row.get("Underlying Asset") or "")
            or (row.get("Ticker") or "")
            or (row.get("symbol") or "")
            or (row.get("Instrument") or "")
        )
        ticker = ticker.strip() if isinstance(ticker, str) else ticker

        if not ticker:
            continue

        leverage_raw = row.get("Leverage")
        try:
            leverage_val = int(str(leverage_raw).strip()) if leverage_raw is not None and str(leverage_raw).strip() != "" else 1
        except Exception:
            leverage_val = 1

        order_time = row.get("Order Time")
        entry_date = parse_datetime(order_time, tz=tz)

        side = row.get("Side", "")
        avg_fill = parse_price(row.get("Avg Fill", ""))
        status = row.get("Status", "")

        action, direction, _reason = infer_action_and_direction(side)
        open_flag = action == "OPEN"
        entry_summary = make_entry_summary(side, status)
        created_at = datetime.utcnow()

        # IMPORTANT: transaction safety
        # Each row executes in its own transaction.
        try:
            with conn.cursor() as cur:
                if open_flag:
                    # Idempotent insert for open trades (no ON CONFLICT)
                    cur.execute(
                        """
                        INSERT INTO trades
                        (ticker, direction, entry_price, exit_price, stop_loss,
                         leverage, entry_date, end_date, entry_summary,
                         orphan_close, source, created_at, source_filename, is_duplicate)
                        SELECT %s,%s,%s,NULL,NULL,
                               %s,%s,NULL,%s,
                               false,%s,%s,%s,false
                        WHERE NOT EXISTS (
                            SELECT 1 FROM trades
                            WHERE ticker=%s
                              AND direction=%s
                              AND entry_price=%s
                              AND entry_date=%s
                              AND end_date IS NULL
                        )
                        """,
                        (
                            ticker,
                            direction,
                            avg_fill,
                            leverage_val,
                            entry_date,
                            entry_summary,
                            SOURCE_NAME,
                            created_at,
                            basename,
                            ticker,
                            direction,
                            avg_fill,
                            entry_date,
                        ),
                    )
                else:
                    # Best-effort: update an open trade, but do not fail the row if update fails
                    try:
                        _ = find_open_trade_and_update(
                            cur,
                            ticker,
                            direction,
                            avg_fill,
                            entry_date,
                            entry_price=avg_fill,
                        )
                    except Exception:
                        pass

                    # Always insert close row (so rows == CSV rows)
                    cur.execute(
                        """
                        INSERT INTO trades
                        (ticker, direction, entry_price, exit_price, stop_loss,
                         leverage, entry_date, end_date, entry_summary,
                         orphan_close, source, created_at, source_filename, is_duplicate)
                        VALUES (%s,%s,%s,%s,NULL,
                                %s,%s,%s,%s,
                                false,%s,%s,%s,false)
                        """,
                        (
                            ticker,
                            direction,
                            avg_fill,
                            avg_fill,
                            leverage_val,
                            entry_date,
                            entry_date,
                            entry_summary,
                            SOURCE_NAME,
                            created_at,
                            basename,
                        ),
                    )

            if dry_run:
                conn.rollback()
            else:
                conn.commit()

            inserted_rows += 1

        except Exception as e:
            failed_rows += 1
            conn.rollback()
            print(f"  -> row {i} failed, continuing (rolled back row txn): {e}")
            # Uncomment next line if you want full stack traces per row in CI logs:
            # print(traceback.format_exc())
            continue

    # Record the file as imported ONLY if we are not dry-run
    # (and do it in its own clean transaction)
    try:
        if dry_run:
            print("  -> dry-run: file hash NOT recorded; no archiving performed")
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO imported_files (filename, file_hash) VALUES (%s, %s)",
                    (basename, file_hash),
                )
            conn.commit()
            print(f"  -> file import committed ({inserted_rows} rows inserted, {failed_rows} row failures)")

            if archive_dir:
                os.makedirs(archive_dir, exist_ok=True)
                dest = os.path.join(archive_dir, basename)
                shutil.move(file_path, dest)
                print(f"  -> moved file to archive: {dest}")

    except Exception as e:
        conn.rollback()
        print("\n  -> ERROR recording imported file hash / archiving (rolled back):")
        print("Exception:", str(e))
        print(traceback.format_exc())
        raise


def gather_input_paths(input_arg):
    if os.path.isdir(input_arg):
        pattern = os.path.join(input_arg, "*.csv")
        return sorted(glob.glob(pattern))
    paths = sorted(glob.glob(input_arg))
    return [p for p in paths if os.path.isfile(p)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", required=True, help="File path, glob, or directory containing CSV(s)")
    p.add_argument("--db", "-d", required=False, default=None, help="psycopg2 DSN (overrides CRYPTO_JOURNAL_DSN env var)")
    p.add_argument("--archive-dir", "-a", required=False, default=None, help="Move processed files here")
    p.add_argument("--tz", "-t", required=False, default=None, help="Timezone of CSV timestamps (e.g. America/Los_Angeles). If set, times will be converted to UTC.")
    p.add_argument("--dry-run", action="store_true", help="Simulate the import without making any changes to the database")
    args = p.parse_args()

    dsn = args.db or os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        raise SystemExit("DB connection string required: use --db or set CRYPTO_JOURNAL_DSN env var")

    paths = gather_input_paths(args.input)
    if not paths:
        print("No CSV files found for input:", args.input)
        return

    conn = psycopg2.connect(dsn)
    try:
        # Warning is informational only; importer works without this index now.
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT indexname FROM pg_indexes WHERE indexname = 'uniq_open_trade_on_fields';")
                if not cur.fetchone():
                    print("\nWARNING: 'uniq_open_trade_on_fields' index is missing! This can cause duplicates for open trades.")
                    print("Run create_unique_index.py or apply migrations to add this index for consistency.\n")
        except Exception:
            # Don't fail just because pg_indexes isn't readable for some reason
            pass

        for path in paths:
            process_file(conn, path, tz=args.tz, archive_dir=args.archive_dir, dry_run=args.dry_run)

    finally:
        conn.close()


if __name__ == "__main__":
    main()

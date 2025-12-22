#!/usr/bin/env python3
"""
Import Blofin CSV(s) into the trades table.

Usage examples:
  # single file
  python import_blofin_csv.py --input "/path/to/Order_history_*.csv" --db "dbname=crypto_journal user=postgres password=secret"

  # directory (process all .csv)
  python import_blofin_csv.py --input "/path/to/csv_dir" --archive-dir "/path/to/archive" --tz "America/Los_Angeles" --db "$CRYPTO_JOURNAL_DSN"

Requirements:
  pip install pandas psycopg2-binary
  Python 3.9+ (for zoneinfo timezone support)
"""
import argparse
import glob
import hashlib
import os
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

SOURCE_NAME = "blofin_order_history"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def parse_price(s):
    if not isinstance(s, str):
        return None
    s = s.strip()
    if s in ("", "--", "Market"):
        return None
    # extract numeric prefix
    import re
    m = re.match(r"([0-9\.\-eE]+)", s)
    return float(m.group(1)) if m else None

def parse_datetime(s, tz=None):
    # CSV format like: 12/19/2025 05:57:22
    try:
        dt = pd.to_datetime(s, format="%m/%d/%Y %H:%M:%S", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return None
        ts = dt.to_pydatetime()
        if tz:
            # localize naive -> tz, then convert to UTC
            local = ts.replace(tzinfo=ZoneInfo(tz))
            return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        else:
            # keep naive (no tz conversion)
            return ts
    except Exception:
        return None

def direction_from_side(side):
    side = (side or "").lower()
    if "long" in side:
        return "LONG"
    if "short" in side:
        return "SHORT"
    return None

def is_open_side(side):
    side = (side or "").lower()
    return side.startswith("open")

def make_entry_summary(side, status):
    side = side or ""
    status = status or ""
    if is_open_side(side):
        return f"Imported: {side}"
    else:
        return f"Imported orphan close: {side}" if status.lower().startswith("filled") else f"Imported close: {side}"

def ensure_imported_files_table(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS imported_files (
      id SERIAL PRIMARY KEY,
      filename TEXT NOT NULL,
      file_hash TEXT NOT NULL UNIQUE,
      imported_at TIMESTAMP DEFAULT now()
    );
    """)

def process_file(conn, file_path, tz=None, archive_dir=None):
    print(f"Processing: {file_path}")
    file_hash = file_sha256(file_path)
    cur = conn.cursor()

    ensure_imported_files_table(cur)
    # Check if we've already imported this file
    cur.execute("SELECT 1 FROM imported_files WHERE file_hash = %s", (file_hash,))
    if cur.fetchone():
        print("  -> already imported (hash match). Skipping.")
        cur.close()
        return

    # Read CSV
    df = pd.read_csv(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    inserts_open = []
    inserts_close = []

    for _, row in df.iterrows():
        ticker = row.get("Underlying Asset") or row.get("Underlying Asset,Margin Mode,Leverage,Order Time,Side,Avg Fill,Price,Filled,Total,PNL,PNL%,Fee,Order Options,Reduce-only,Status")
        leverage = row.get("Leverage")
        leverage_val = int(leverage) if pd.notna(leverage) and str(leverage).strip() != "" else 1
        order_time = row.get("Order Time")
        entry_date = parse_datetime(order_time, tz=tz)
        side = row.get("Side", "")
        avg_fill = parse_price(row.get("Avg Fill", ""))
        status = row.get("Status", "")

        direction = direction_from_side(side)
        open_flag = is_open_side(side)
        entry_summary = make_entry_summary(side, status)

        rec = {
            "ticker": ticker,
            "direction": direction,
            "entry_price": avg_fill,
            "exit_price": None,
            "stop_loss": None,
            "leverage": leverage_val,
            "entry_date": entry_date,
            "end_date": None,
            "entry_summary": entry_summary,
            "orphan_close": False,
            "source": SOURCE_NAME,
            "created_at": datetime.utcnow()
        }

        if open_flag:
            inserts_open.append(rec)
        else:
            rec["end_date"] = entry_date
            rec["exit_price"] = avg_fill
            inserts_close.append(rec)

    try:
        # Insert close trades first
        if inserts_close:
            vals = [
                (
                    r["ticker"], r["direction"], r["entry_price"], r["exit_price"],
                    r["stop_loss"], r["leverage"], r["entry_date"], r["end_date"],
                    r["entry_summary"], r["orphan_close"], r["source"], r["created_at"], False
                )
                for r in inserts_close
            ]
            execute_values(cur, """
            INSERT INTO trades
            (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, is_duplicate)
            VALUES %s
            """, vals, page_size=200)
            print(f"  -> inserted {len(vals)} close trades")

        # Insert open trades using ON CONFLICT on business key
        if inserts_open:
            vals = [
                (
                    r["ticker"], r["direction"], r["entry_price"], r["exit_price"],
                    r["stop_loss"], r["leverage"], r["entry_date"], r["end_date"],
                    r["entry_summary"], r["orphan_close"], r["source"], r["created_at"], False
                )
                for r in inserts_open
            ]
            execute_values(cur, """
            INSERT INTO trades
            (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, is_duplicate)
            VALUES %s
            ON CONFLICT (ticker, direction, entry_date, entry_price) DO NOTHING
            """, vals, page_size=200)
            print(f"  -> attempted insert {len(vals)} open trades (duplicates skipped)")

        # Record the file as imported
        cur.execute("INSERT INTO imported_files (filename, file_hash) VALUES (%s, %s)", (os.path.basename(file_path), file_hash))

        conn.commit()
        print("  -> file import committed")

        # Optionally archive the file
        if archive_dir:
            os.makedirs(archive_dir, exist_ok=True)
            dest = os.path.join(archive_dir, os.path.basename(file_path))
            shutil.move(file_path, dest)
            print(f"  -> moved file to archive: {dest}")

    except Exception as e:
        conn.rollback()
        print("  -> ERROR during import, transaction rolled back:", e)
    finally:
        cur.close()

def gather_input_paths(input_arg):
    # If input is a directory, find *.csv inside
    if os.path.isdir(input_arg):
        pattern = os.path.join(input_arg, "*.csv")
        return sorted(glob.glob(pattern))
    # If glob pattern or single file
    paths = sorted(glob.glob(input_arg))
    return [p for p in paths if os.path.isfile(p)]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", required=True, help="File path, glob, or directory containing CSV(s)")
    p.add_argument("--db", "-d", required=False, default=None, help="psycopg2 DSN (overrides CRYPTO_JOURNAL_DSN env var)")
    p.add_argument("--archive-dir", "-a", required=False, default=None, help="Move processed files here")
    p.add_argument("--tz", "-t", required=False, default=None, help="Timezone of CSV timestamps (e.g. America/Los_Angeles). If set, times will be converted to UTC.")
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
        for path in paths:
            process_file(conn, path, tz=args.tz, archive_dir=args.archive_dir)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
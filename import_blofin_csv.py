#!/usr/bin/env python3
"""
Import Blofin CSV(s) into the trades table.

Usage examples:
  # single file
  python import_blofin_csv.py --input "/path/to/Order_history_*.csv" --db "dbname=crypto_journal user=postgres password=secret"

  # directory (process all .csv)
  python import_blofin_csv.py --input "/path/to/csv_dir" --archive-dir "/path/to/archive" --tz "America/Los_Angeles" --db "$CRYPTO_JOURNAL_DSN"

  # dry-run mode (no changes committed)
  python import_blofin_csv.py --input "/path/to/Order_history_*.csv" --tz "America/Los_Angeles" --dry-run

Requirements:
  pip install pandas psycopg2-binary
  Python 3.9+ (for zoneinfo timezone support)
"""
import argparse
import glob
import hashlib
import os
import shutil
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

SOURCE_NAME = "blofin_order_history"

# Add app utils to path so we can import side_parser
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
try:
    from utils.side_parser import infer_action_and_direction
except ImportError:
    # Fallback if module not available
    def infer_action_and_direction(side):
        return None, None, None

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
    """Extract direction from side string - uses robust parser if available."""
    action, direction, reason = infer_action_and_direction(side)
    return direction  # Returns "LONG" or "SHORT" or None

def is_open_side(side):
    """Check if this is an opening trade - uses robust parser if available."""
    action, direction, reason = infer_action_and_direction(side)
    return action == "OPEN"

def make_entry_summary(side, status, reason=None):
    """Generate entry summary with action and reason if available."""
    action, direction, parsed_reason = infer_action_and_direction(side)
    reason = reason or parsed_reason
    
    if action == "OPEN":
        return f"Imported: {side}"
    elif action == "CLOSE":
        if reason:
            return f"Imported close ({reason}): {side}"
        if status and status.lower().startswith("filled"):
            return f"Imported orphan close: {side}"
        return f"Imported close: {side}"
    else:
        # Fallback for unparsable side
        return f"Imported: {side}"

def ensure_imported_files_table(dsn):
    """Ensure the imported_files table exists using the environment DSN."""
    # Use a fresh connection with the provided DSN to avoid password issues
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS imported_files (
          id SERIAL PRIMARY KEY,
          filename TEXT NOT NULL,
          file_hash TEXT NOT NULL UNIQUE,
          imported_at TIMESTAMP DEFAULT now()
        );
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()

def detect_ticker_column(df):
    """Detect the ticker column from multiple possible column names."""
    possible_names = [
        "Underlying Asset",
        "Underlying",
        "Asset",
        "Symbol",
        "Ticker"
    ]
    
    # Check if first column contains ticker data (malformed CSV header)
    first_col = df.columns[0]
    if "Underlying Asset" in first_col or "," in first_col:
        # Malformed header with comma-separated values
        return first_col
    
    # Check standard column names
    for name in possible_names:
        if name in df.columns:
            return name
    
    # Fallback to first column
    return df.columns[0] if len(df.columns) > 0 else None

def process_file(conn, file_path, tz=None, archive_dir=None, dry_run=False):
    print(f"Processing: {file_path}")
    if dry_run:
        print("  -> DRY-RUN MODE: Changes will not be committed")
    
    file_hash = file_sha256(file_path)
    cur = conn.cursor()

    try:
        # Check if we've already imported this file
        cur.execute("SELECT 1 FROM imported_files WHERE file_hash = %s", (file_hash,))
        if cur.fetchone():
            print("  -> already imported (hash match). Skipping.")
            cur.close()
            return

        # Read CSV
        df = pd.read_csv(file_path, dtype=str)
        df.columns = [c.strip() for c in df.columns]

        # Detect ticker column
        ticker_col = detect_ticker_column(df)
        if not ticker_col:
            print("  -> ERROR: Could not detect ticker column")
            return

        inserts_open = []
        inserts_close = []

        for _, row in df.iterrows():
            ticker = row.get(ticker_col, "")
            if pd.isna(ticker) or not ticker:
                continue
                
            leverage = row.get("Leverage", "")
            leverage_val = int(leverage) if pd.notna(leverage) and str(leverage).strip() != "" else 1
            order_time = row.get("Order Time", "")
            entry_date = parse_datetime(order_time, tz=tz)
            side = row.get("Side", "")
            avg_fill = parse_price(row.get("Avg Fill", ""))
            status = row.get("Status", "")

            # Use robust side parser
            action, direction, reason = infer_action_and_direction(side)
            open_flag = (action == "OPEN")
            entry_summary = make_entry_summary(side, status, reason)

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
            print(f"  -> parsed {len(vals)} close trades")

        # Insert open trades with ON CONFLICT fallback
        if inserts_open:
            vals = [
                (
                    r["ticker"], r["direction"], r["entry_price"], r["exit_price"],
                    r["stop_loss"], r["leverage"], r["entry_date"], r["end_date"],
                    r["entry_summary"], r["orphan_close"], r["source"], r["created_at"], False
                )
                for r in inserts_open
            ]
            
            # Try multi-row INSERT with ON CONFLICT first (fast path)
            try:
                execute_values(cur, """
                INSERT INTO trades
                (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, is_duplicate)
                VALUES %s
                ON CONFLICT (ticker, direction, entry_date, entry_price) DO NOTHING
                """, vals, page_size=200)
                print(f"  -> processed {len(vals)} open trades (duplicates skipped via ON CONFLICT)")
            except psycopg2.Error as e:
                # ON CONFLICT failed - likely missing unique index
                # Rollback and use fallback approach
                conn.rollback()
                cur = conn.cursor()  # Get new cursor after rollback
                
                print(f"  -> WARNING: ON CONFLICT failed (missing unique index?), using fallback INSERT WHERE NOT EXISTS")
                print(f"     Error was: {e}")
                
                # Fallback: per-row INSERT WHERE NOT EXISTS
                inserted = 0
                for val in vals:
                    try:
                        cur.execute("""
                        INSERT INTO trades
                        (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, is_duplicate)
                        SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM trades
                            WHERE ticker = %s
                              AND direction = %s
                              AND entry_date = %s
                              AND entry_price = %s
                        )
                        """, val + (val[0], val[1], val[6], val[2]))
                        if cur.rowcount > 0:
                            inserted += 1
                    except Exception as row_err:
                        print(f"     -> Failed to insert row: {row_err}")
                        continue
                
                print(f"  -> processed {len(vals)} open trades via fallback ({inserted} new, {len(vals)-inserted} skipped)")

        # Record the file as imported
        cur.execute("INSERT INTO imported_files (filename, file_hash) VALUES (%s, %s)", 
                   (os.path.basename(file_path), file_hash))

        if dry_run:
            conn.rollback()
            print("  -> DRY-RUN: transaction rolled back (no changes committed)")
        else:
            conn.commit()
            print("  -> file import committed")

            # Optionally archive the file (only in real mode)
            if archive_dir:
                os.makedirs(archive_dir, exist_ok=True)
                dest = os.path.join(archive_dir, os.path.basename(file_path))
                shutil.move(file_path, dest)
                print(f"  -> moved file to archive: {dest}")

    except Exception as e:
        conn.rollback()
        print("  -> ERROR during import, transaction rolled back:")
        print(traceback.format_exc())
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
    p.add_argument("--dry-run", required=False, action="store_true", help="Simulate import without committing changes to the database")
    args = p.parse_args()

    dsn = args.db or os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        raise SystemExit("DB connection string required: use --db or set CRYPTO_JOURNAL_DSN env var")

    # Ensure imported_files table exists using environment DSN
    ensure_imported_files_table(dsn)

    paths = gather_input_paths(args.input)
    if not paths:
        print("No CSV files found for input:", args.input)
        return

    conn = psycopg2.connect(dsn)
    try:
        for path in paths:
            process_file(conn, path, tz=args.tz, archive_dir=args.archive_dir, dry_run=args.dry_run)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
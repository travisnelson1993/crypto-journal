#!/usr/bin/env python3
"""
Import Blofin CSV(s) into the trades table.

CI-SAFE MODE
-------------
• NO ON CONFLICT
• NO savepoints
• WHERE NOT EXISTS idempotency
• Transaction-safe
• Works even if uniq_open_trade_on_fields index is missing
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


# ───────────────────────── helpers ─────────────────────────

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
    try:
        return float(s)
    except Exception:
        return None


def parse_datetime(s, tz=None):
    dt = pd.to_datetime(s, errors="coerce")
    if pd.isna(dt):
        return None
    ts = dt.to_pydatetime()
    if tz:
        ts = ts.replace(tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))
        return ts.replace(tzinfo=None)
    return ts


def make_entry_summary(side, status):
    side = side or ""
    status = status or ""
    if side.lower().startswith("open"):
        return f"Imported: {side}"
    return f"Imported close: {side}"


def ensure_imported_files_table(cur):
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


# ───────────────────────── core ─────────────────────────

def process_file(conn, file_path, tz=None, archive_dir=None, dry_run=False):
    print(f"Processing: {file_path}")
    basename = os.path.basename(file_path)
    file_hash = file_sha256(file_path)

    cur = conn.cursor()

    try:
        # Ensure imported_files exists
        ensure_imported_files_table(cur)

        # Skip already imported file (hash-based)
        cur.execute(
            "SELECT 1 FROM imported_files WHERE file_hash = %s",
            (file_hash,),
        )
        if cur.fetchone():
            print("  -> already imported (hash match). Skipping.")
            return

        df = pd.read_csv(file_path, dtype=str)
        df.columns = [c.strip() for c in df.columns]

        for _, row in df.iterrows():
            ticker = (
                row.get("Underlying Asset")
                or row.get("Ticker")
                or row.get("symbol")
                or row.get("Instrument")
            )
            if not ticker:
                continue

            side = row.get("Side", "")
            status = row.get("Status", "")
            leverage = int(row.get("Leverage") or 1)
            price = parse_price(row.get("Avg Fill"))
            entry_date = parse_datetime(row.get("Order Time"), tz)

            action, direction, _ = infer_action_and_direction(side)
            is_open = action == "OPEN"
            entry_summary = make_entry_summary(side, status)

            created_at = datetime.utcnow()

            if is_open:
                # ── SAFE OPEN INSERT ──
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
                        price,
                        leverage,
                        entry_date,
                        entry_summary,
                        SOURCE_NAME,
                        created_at,
                        basename,
                        ticker,
                        direction,
                        price,
                        entry_date,
                    ),
                )

            else:
                # ── CLOSE ROW (ALWAYS INSERT) ──
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
                        price,
                        price,
                        leverage,
                        entry_date,
                        entry_date,
                        entry_summary,
                        SOURCE_NAME,
                        created_at,
                        basename,
                    ),
                )

        # Record imported file
        cur.execute(
            "INSERT INTO imported_files (filename, file_hash) VALUES (%s,%s)",
            (basename, file_hash),
        )

        if dry_run:
            conn.rollback()
            print("  -> dry-run: rolled back")
        else:
            conn.commit()
            print("  -> file import committed")

        if archive_dir and not dry_run:
            os.makedirs(archive_dir, exist_ok=True)
            shutil.move(file_path, os.path.join(archive_dir, basename))

    except Exception as e:
        conn.rollback()
        print("\n  -> ERROR during import, transaction rolled back:")
        print(e)
        print(traceback.format_exc())
        raise

    finally:
        cur.close()


def gather_input_paths(input_arg):
    if os.path.isdir(input_arg):
        return sorted(glob.glob(os.path.join(input_arg, "*.csv")))
    return sorted(glob.glob(input_arg))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", required=True)
    p.add_argument("--db", "-d", default=None)
    p.add_argument("--archive-dir", "-a", default=None)
    p.add_argument("--tz", "-t", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    dsn = args.db or os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        raise SystemExit("CRYPTO_JOURNAL_DSN not set")

    paths = gather_input_paths(args.input)
    if not paths:
        print("No CSV files found.")
        return

    conn = psycopg2.connect(dsn)
    try:
        for path in paths:
            process_file(
                conn,
                path,
                tz=args.tz,
                archive_dir=args.archive_dir,
                dry_run=args.dry_run,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Import Blofin CSV(s) into the trades table.

CI-SAFE MODE
-------------
- NO ON CONFLICT
- Uses SAVEPOINT per-row so one bad row cannot poison the whole transaction
- WHERE NOT EXISTS idempotency for OPEN rows
- Always inserts CLOSE rows (so CSV row count == trade row count)
- Works even if uniq_open_trade_on_fields index is missing
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


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_price(s):
    """
    Parses numbers that may include extra text. Returns float or None.
    """
    if s is None:
        return None
    if not isinstance(s, str):
        # pandas can hand us NaN floats or other types
        try:
            if pd.isna(s):
                return None
        except Exception:
            pass
        return None

    s = s.strip()
    if s in ("", "--", "Market"):
        return None

    # tolerate things like "123.45 USDT" or "1.23e-4"
    import re

    m = re.match(r"([0-9\.\-eE]+)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def parse_datetime(s, tz=None):
    """
    Returns naive UTC datetime if tz provided, else returns naive parsed datetime.
    """
    dt = pd.to_datetime(s, errors="coerce")
    if pd.isna(dt):
        return None
    ts = dt.to_pydatetime()
    if tz:
        ts = ts.replace(tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))
        return ts.replace(tzinfo=None)
    return ts


def make_entry_summary(side, status):
    side = (side or "").strip()
    status = (status or "").strip()
    if side.lower().startswith("open"):
        return f"Imported: {side}"
    return f"Imported close: {side}"


def safe_int(val, default=1) -> int:
    if val is None:
        return default
    if isinstance(val, (int,)):
        return int(val)
    if isinstance(val, float):
        try:
            if pd.isna(val):
                return default
        except Exception:
            pass
        return int(val)
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return default
    try:
        return int(float(s))
    except Exception:
        return default


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


def create_savepoint_name(prefix: str, i: int) -> str:
    # Keep it simple/safe for SQL identifiers.
    return f"{prefix}_{i}"


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

        for i, row in enumerate(df.to_dict(orient="records")):
            ticker = (
                row.get("Underlying Asset")
                or row.get("Ticker")
                or row.get("symbol")
                or row.get("Instrument")
            )
            ticker = ticker.strip() if isinstance(ticker, str) else ticker
            if not ticker:
                continue

            side = row.get("Side", "") or ""
            status = row.get("Status", "") or ""
            leverage = safe_int(row.get("Leverage"), default=1)
            price = parse_price(row.get("Avg Fill"))
            entry_date = parse_datetime(row.get("Order Time"), tz)

            action, direction, _ = infer_action_and_direction(side)
            is_open = action == "OPEN"
            entry_summary = make_entry_summary(side, status)
            created_at = datetime.utcnow()

            if is_open:
                # ── SAFE OPEN INSERT (SAVEPOINT protected) ──
                sp = create_savepoint_name("sp_open", i)
                cur.execute(f"SAVEPOINT {sp}")
                try:
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
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception:
                    # Do not poison transaction: rollback only this row
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    # (optional) keep going
                    # cur.execute(f"RELEASE SAVEPOINT {sp}")  # not strictly necessary after rollback in PG

            else:
                # ── CLOSE ROW (ALWAYS INSERT) (SAVEPOINT protected) ──
                sp = create_savepoint_name("sp_close", i)
                cur.execute(f"SAVEPOINT {sp}")
                try:
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
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    # keep going

        # Record imported file (SAVEPOINT protected too, just in case)
        cur.execute("SAVEPOINT sp_file_record")
        try:
            cur.execute(
                "INSERT INTO imported_files (filename, file_hash) VALUES (%s,%s)",
                (basename, file_hash),
            )
            cur.execute("RELEASE SAVEPOINT sp_file_record")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT sp_file_record")
            # If we can't record the file, we should fail; otherwise we’ll re-import forever.
            raise

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
        try:
            cur.close()
        except Exception:
            pass


def gather_input_paths(input_arg):
    if os.path.isdir(input_arg):
        return sorted(glob.glob(os.path.join(input_arg, "*.csv")))
    return [p for p in sorted(glob.glob(input_arg)) if os.path.isfile(p)]


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
        raise SystemExit("CRYPTO_JOURNAL_DSN not set (or pass --db)")

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

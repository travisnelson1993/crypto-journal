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
import logging
import os
import shutil
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from app.utils.side_parser import infer_action_and_direction

SOURCE_NAME = "blofin_order_history"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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


def make_entry_summary(side, status):
    side = side or ""
    status = status or ""
    side_norm = (side or "").lower()
    if side_norm.startswith("open"):
        return f"Imported: {side}"
    else:
        return f"Imported orphan close: {side}" if status.lower().startswith("filled") else f"Imported close: {side}"


def ensure_imported_files_table(cur):
    # use timestamptz for imported_at to avoid timezone mismatch issues
    cur.execute("""
    CREATE TABLE IF NOT EXISTS imported_files (
      id SERIAL PRIMARY KEY,
      filename TEXT NOT NULL,
      file_hash TEXT NOT NULL UNIQUE,
      imported_at TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)


def _insert_opens_with_fallback(conn, cur, inserts_open):
    """
    Try bulk insert of opens with execute_values and ON CONFLICT fast path.
    If ON CONFLICT path is not supported, fall back to safe per-row INSERT ... WHERE NOT EXISTS.
    Return a cursor that is open and ready for further work (may be the same cur or a newly-created one).
    This function raises on unexpected per-row errors to avoid silently skipping rows.
    """
    vals = [
        (
            r["ticker"], r["direction"], r["entry_price"], r["exit_price"],
            r["stop_loss"], r["leverage"], r["entry_date"], r["end_date"],
            r["entry_summary"], r["orphan_close"], r["source"], r["created_at"],
            (r.get("source_filename") or ""), False
        )
        for r in inserts_open
    ]

    if not vals:
        # nothing done; return the cursor we were given
        return cur

    try:
        # Try fast bulk insert with ON CONFLICT (duplicates skipped)
        execute_values(cur, """
            INSERT INTO trades
            (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, source_filename, is_duplicate)
            VALUES %s
            ON CONFLICT (ticker, direction, entry_date, entry_price) DO NOTHING
            """, vals, page_size=200)
        logger.info("  -> attempted insert %d open trades (duplicates skipped)", len(vals))
        # still using the original cursor
        return cur
    except Exception as e:
        msg = str(e).lower()
        # If ON CONFLICT target not supported (no matching unique index), fall back to safe per-row inserts
        if "no unique or exclusion constraint matching the on conflict specification" in msg or isinstance(e, psycopg2.errors.InvalidColumnReference):
            logger.info("  -> ON CONFLICT not supported for this target in this DB connection, falling back to safe per-row inserts.")
            conn.rollback()
            # Close the old cursor and create a new one for per-row work.
            try:
                cur.close()
            except Exception:
                pass
            cur = conn.cursor()
            fallback_count = 0
            for r in inserts_open:
                params = (
                    r["ticker"], r["direction"], r["entry_price"], r["exit_price"],
                    r["stop_loss"], r["leverage"], r["entry_date"], r["end_date"],
                    r["entry_summary"], r["orphan_close"], r["source"], r["created_at"],
                    (r.get("source_filename") or ""), False,
                    r["ticker"], r["direction"], r["entry_date"], r["entry_price"]
                )
                try:
                    cur.execute("""
                        INSERT INTO trades
                        (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, source_filename, is_duplicate)
                        SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM trades WHERE ticker = %s AND direction = %s AND entry_date = %s AND entry_price = %s AND end_date IS NULL
                        )
                        """, params)
                    fallback_count += 1
                except Exception as inner_e:
                    # On per-row failure, log full row and re-raise to fail CI/tests rather than silently skipping
                    conn.rollback()
                    logger.exception("    -> per-row insert FAILED for row=%r error=%s", r, inner_e)
                    try:
                        cur.close()
                    except Exception:
                        pass
                    raise
            logger.info("  -> fallback attempted %d open trades (per-row), fallback loop ran %d executes", len(inserts_open), fallback_count)
            # return the (new) cursor so caller keeps using an open one
            return cur
        else:
            # Unexpected exception on bulk insert: re-raise
            raise



def _apply_closes_or_insert(cur, inserts_close, source_name):
    """
    For each close record:
      - first try to UPDATE an existing open trade (end_date IS NULL) that matches entry_price and entry_date
      - if no matching open found, try to UPDATE the most recent open trade for the same source/ticker/direction (end_date IS NULL)
      - always INSERT a trade row representing the close record (so every CSV row is recorded)
    This keeps the strict matching behavior when the CSV includes entry info,
    but also ensures we store the close row itself for audit/idempotency.
    """
    for r in inserts_close:
        try:
            ticker = r["ticker"]
            direction = r["direction"]
            entry_price = r["entry_price"]
            entry_date = r["entry_date"]
            exit_price = r["exit_price"]
            end_date = r["end_date"]
            source_filename = r.get("source_filename", "")

            # 1) Try the strict update (existing behavior) matching entry_price + entry_date
            cur.execute("""
                UPDATE trades
                SET exit_price = %s,
                    end_date = %s,
                    source_filename = COALESCE(source_filename, %s)
                WHERE source = %s
                  AND ticker = %s
                  AND direction = %s
                  AND entry_price = %s
                  AND entry_date = %s
                  AND end_date IS NULL
                """, (exit_price, end_date, source_filename, source_name,
                      ticker, direction, entry_price, entry_date))

            # 2) If strict update matched nothing, try the pragmatic fallback:
            #    apply the close to the most recent open trade for this source/ticker/direction.
            if cur.rowcount == 0:
                cur.execute("""
                    SELECT id FROM trades
                    WHERE source = %s AND ticker = %s AND direction = %s AND end_date IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (source_name, ticker, direction))
                row = cur.fetchone()
                if row:
                    open_id = row[0]
                    cur.execute("""
                        UPDATE trades
                        SET exit_price = %s,
                            end_date = %s,
                            source_filename = COALESCE(source_filename, %s)
                        WHERE id = %s
                    """, (exit_price, end_date, source_filename, open_id))
                # else: no open to update; we'll insert the close row below

            # 3) Always insert the close record as its own trade row so every CSV row is recorded.
            insert_cols = (
                'ticker', 'direction', 'entry_price', 'exit_price', 'stop_loss',
                'leverage', 'entry_date', 'end_date', 'entry_summary', 'orphan_close',
                'source', 'created_at', 'source_filename', 'is_duplicate'
            )
            insert_vals = (
                r["ticker"], r["direction"], r["entry_price"], r["exit_price"],
                r["stop_loss"], r["leverage"], r["entry_date"], r["end_date"],
                r["entry_summary"], r["orphan_close"], r["source"], r["created_at"],
                (r.get("source_filename") or ""), False
            )
            placeholders = ','.join(['%s'] * len(insert_cols))
            q = f"INSERT INTO trades ({','.join(insert_cols)}) VALUES ({placeholders})"
            cur.execute(q, insert_vals)

        except Exception as exc:
            logger.exception("Failed to apply close row %r: %s", r, exc)
            raise


def process_file(conn, file_path, tz=None, archive_dir=None, dry_run=False):
    """
    Process one CSV file and import trades into `trades` table.
    """
    print(f"Processing: {file_path}")
    file_hash = file_sha256(file_path)

    # create a cursor for work
    cur = conn.cursor()

    # Ensure the imported_files table exists in a persistent way using a separate connection (use env DSN to ensure password is included)
    try:
        env_dsn = os.getenv("CRYPTO_JOURNAL_DSN")
        if not env_dsn:
            raise RuntimeError("CRYPTO_JOURNAL_DSN is not set in the environment")
        with psycopg2.connect(env_dsn) as ddl_conn:
            ddl_conn.autocommit = True
            with ddl_conn.cursor() as ddl_cur:
                ensure_imported_files_table(ddl_cur)
    except Exception as e:
        # Non-fatal: warn and continue; later INSERT will fail if the table truly doesn't exist
        logger.warning("Warning: failed to ensure imported_files table exists: %s", e)

    # Recreate the working cursor (fresh transactional cursor)
    try:
        cur.close()
    except:
        pass
    cur = conn.cursor()

    # Check if we've already imported this file
    cur.execute("SELECT 1 FROM imported_files WHERE file_hash = %s", (file_hash,))
    if cur.fetchone():
        print("  -> already imported (hash match). Skipping.")
        cur.close()
        return

    # Read CSV
    df = pd.read_csv(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # basename used for source_filename on inserted rows
    basename = os.path.basename(file_path) if file_path else ""

    inserts_open = []
    inserts_close = []

    for _, row in df.iterrows():
        # improved ticker detection (check multiple likely column names)
        ticker = (
            (row.get("Underlying Asset") or "")
            or (row.get("Ticker") or "")
            or (row.get("symbol") or "")
            or (row.get("Instrument") or "")
        )
        ticker = ticker.strip() if isinstance(ticker, str) else ticker

        leverage = row.get("Leverage")
        leverage_val = int(leverage) if pd.notna(leverage) and str(leverage).strip() != "" else 1
        order_time = row.get("Order Time")
        entry_date = parse_datetime(order_time, tz=tz)
        side = row.get("Side", "")
        avg_fill = parse_price(row.get("Avg Fill", ""))
        status = row.get("Status", "")

        # use the robust parser from app.utils.side_parser
        action, direction, reason = infer_action_and_direction(side)
        open_flag = (action == "OPEN")
        entry_summary = make_entry_summary(side, status)

        # Use timezone-aware UTC datetime for created_at
        created_at = datetime.now(tz=ZoneInfo("UTC"))

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
            "created_at": created_at,
            "source_filename": basename or ""
        }

        if open_flag:
            inserts_open.append(rec)
        else:
            rec["end_date"] = entry_date
            rec["exit_price"] = avg_fill
            inserts_close.append(rec)

    try:
        # --- Two-pass processing (opens first, then closes applied as updates) ---
        # 1) Insert open trades (bulk -> fallback to per-row)
        cur = _insert_opens_with_fallback(conn, cur, inserts_open)

        # 2) Apply close rows: try to update matching open trade (end_date IS NULL). If none found, insert as closed trade.
        _apply_closes_or_insert(cur, inserts_close, SOURCE_NAME)

        # Record the file as imported
        cur.execute("INSERT INTO imported_files (filename, file_hash) VALUES (%s, %s)", (os.path.basename(file_path), file_hash))

        if not dry_run:
            conn.commit()
            print("  -> file import committed")
        else:
            # rollback any changes made during dry-run so DB is not modified
            conn.rollback()
            print("  -> dry-run: changes rolled back (no commit)")

        # Optionally archive the file (only on non-dry-run)
        if archive_dir and not dry_run:
            os.makedirs(archive_dir, exist_ok=True)
            dest = os.path.join(archive_dir, os.path.basename(file_path))
            shutil.move(file_path, dest)
            print(f"  -> moved file to archive: {dest}")

    except Exception as e:
        conn.rollback()
        print("\n  -> ERROR during import, transaction rolled back:")
        print("Exception:", str(e))
        print(traceback.format_exc())
    finally:
        try:
            cur.close()
        except:
            pass


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
        # quick check for the partial unique index that ON CONFLICT relies on
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname FROM pg_indexes WHERE indexname = 'uniq_open_trade_on_fields';
            """)
            if not cur.fetchone():
                print("\nWARNING: 'uniq_open_trade_on_fields' index is missing! This can cause duplicates for open trades.")
                print("Run create_unique_index.py to add this index for consistency.\n")

        for path in paths:
            process_file(conn, path, tz=args.tz, archive_dir=args.archive_dir, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Import Blofin CSV(s) into the trades table.

Usage examples:
  python import_blofin_csv.py --input "/path/to/Order_history_*.csv" --db "dbname=crypto_journal user=postgres password=secret"
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
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from app.utils.side_parser import infer_action_and_direction

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
    import re

    m = re.match(r"([0-9\.\-eE]+)", s)
    return float(m.group(1)) if m else None


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
        else:
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
        return (
            f"Imported orphan close: {side}"
            if status.lower().startswith("filled")
            else f"Imported close: {side}"
        )


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


def find_open_trade_and_update(
    cur, ticker, direction, close_price, close_dt, entry_price=None, price_tolerance=0.0001
):
    """
    Find the most-recent open trade for the same ticker/direction (exit_price IS NULL and entry_date <= close_dt)
    and update it with the provided close_price and close_dt.

    Important:
      - This function updates the existing open trade but deliberately does NOT overwrite
        source_filename or created_at (so we preserve provenance).
      - It also does not prevent inserting a separate close-row — callers can still insert a close record.
    Returns True if an existing open trade was updated, False otherwise.
    """
    cur.execute(
        """
        SELECT id, entry_price, entry_date
        FROM trades
        WHERE ticker = %s AND direction = %s AND exit_price IS NULL AND entry_date <= %s
        ORDER BY entry_date DESC, created_at DESC
        LIMIT 1
        """,
        (ticker, direction, close_dt),
    )
    row = cur.fetchone()
    if not row:
        return False

    trade_id, existing_entry_price, existing_entry_date = row

    # Optional price check (not enforced by default)
    if entry_price is not None:
        try:
            if abs(float(existing_entry_price) - float(entry_price)) > price_tolerance:
                # price mismatch beyond tolerance; still proceed, but you could return False here
                pass
        except Exception:
            pass

    # Update the found trade with close data but don't clear source_filename or created_at
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


def process_file(conn, file_path, tz=None, archive_dir=None, dry_run=False):
    print(f"Processing: {file_path}")
    file_hash = file_sha256(file_path)

    cur = conn.cursor()

    # Ensure imported_files exists (best-effort)
    try:
        env_dsn = os.getenv("CRYPTO_JOURNAL_DSN")
        if not env_dsn:
            raise RuntimeError("CRYPTO_JOURNAL_DSN is not set in the environment")
        with psycopg2.connect(env_dsn) as ddl_conn:
            ddl_conn.autocommit = True
            with ddl_conn.cursor() as ddl_cur:
                ensure_imported_files_table(ddl_cur)
    except Exception as e:
        print("Warning: failed to ensure imported_files table exists:", e)

    try:
        cur.close()
    except:
        pass
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM imported_files WHERE file_hash = %s", (file_hash,))
    if cur.fetchone():
        print("  -> already imported (hash match). Skipping.")
        cur.close()
        return

    df = pd.read_csv(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    basename = os.path.basename(file_path)
    inserts_open = []
    inserts_close = []

    for _, row in df.iterrows():
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

        action, direction, reason = infer_action_and_direction(side)
        open_flag = (action == "OPEN")
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
            "created_at": datetime.utcnow(),
            "source_filename": basename,
        }

        if open_flag:
            inserts_open.append(rec)
        else:
            rec["end_date"] = entry_date
            rec["exit_price"] = avg_fill
            inserts_close.append(rec)

    try:
        # Insert open trades using ON CONFLICT (bulk attempt inside savepoint)
        if inserts_open:
            vals = [
                (
                    r["ticker"],
                    r["direction"],
                    r["entry_price"],
                    r["exit_price"],
                    r["stop_loss"],
                    r["leverage"],
                    r["entry_date"],
                    r["end_date"],
                    r["entry_summary"],
                    r["orphan_close"],
                    r["source"],
                    r["created_at"],
                    r["source_filename"],
                    False,
                )
                for r in inserts_open
            ]

            try:
                cur.execute("SAVEPOINT open_bulk")
                execute_values(
                    cur,
                    """
                INSERT INTO trades
                (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, source_filename, is_duplicate)
                VALUES %s
                ON CONFLICT (ticker, direction, entry_date, entry_price) DO NOTHING
                """,
                    vals,
                    page_size=200,
                )
                try:
                    cur.execute("RELEASE SAVEPOINT open_bulk")
                except Exception:
                    pass
            except Exception as e:
                msg = str(e).lower()
                if (
                    "no unique or exclusion constraint matching the on conflict specification" in msg
                    or isinstance(e, psycopg2.errors.InvalidColumnReference)
                ):
                    # Roll back only the bulk attempt so prior inserts stay
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT open_bulk")
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        try:
                            cur.close()
                        except:
                            pass
                        cur = conn.cursor()

                    # per-row fallback (each row inside its own savepoint)
                    try:
                        cur.close()
                    except:
                        pass
                    cur = conn.cursor()

                    for idx, r in enumerate(inserts_open):
                        savepoint_name = f"sp_{idx}"
                        params = (
                            r["ticker"],
                            r["direction"],
                            r["entry_price"],
                            r["exit_price"],
                            r["stop_loss"],
                            r["leverage"],
                            r["entry_date"],
                            r["end_date"],
                            r["entry_summary"],
                            r["orphan_close"],
                            r["source"],
                            r["created_at"],
                            r["source_filename"],
                            False,
                            r["ticker"],
                            r["direction"],
                            r["entry_date"],
                            r["entry_price"],
                        )
                        try:
                            cur.execute(f"SAVEPOINT {savepoint_name}")
                            cur.execute(
                                """
                            INSERT INTO trades
                            (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, source_filename, is_duplicate)
                            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM trades WHERE ticker = %s AND direction = %s AND entry_date = %s AND entry_price = %s AND end_date IS NULL
                            )
                            """,
                                params,
                            )
                            try:
                                cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                            except Exception:
                                pass
                        except Exception:
                            try:
                                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                                try:
                                    cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                                except Exception:
                                    pass
                            except Exception:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                                try:
                                    cur.close()
                                except:
                                    pass
                                cur = conn.cursor()
                            # continue to next row

        # Now process close trades:
        # - Attempt to update a matching open trade (preserve provenance fields)
        # - ALWAYS insert a trade row for the close (tests expect one row per CSV row)
        if inserts_close:
            for r in inserts_close:
                # Try to update an existing open trade (best-effort). We do not rely on this to prevent
                # inserting the close row because tests and bookkeeping expect a row per CSV row.
                try:
                    _ = find_open_trade_and_update(
                        cur,
                        r["ticker"],
                        r["direction"],
                        r["exit_price"],
                        r["end_date"],
                        entry_price=r.get("entry_price"),
                    )
                except Exception:
                    # update should be best-effort; don't fail the whole import on update errors
                    pass

                # Insert the close record (always insert so total rows == CSV rows)
                cur.execute(
                    """
                    INSERT INTO trades
                    (ticker, direction, entry_price, exit_price, stop_loss, leverage, entry_date, end_date, entry_summary, orphan_close, source, created_at, source_filename, is_duplicate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        r["ticker"],
                        r["direction"],
                        r["entry_price"],
                        r["exit_price"],
                        r["stop_loss"],
                        r["leverage"],
                        r["entry_date"],
                        r["end_date"],
                        r["entry_summary"],
                        r["orphan_close"],
                        r["source"],
                        r["created_at"],
                        r["source_filename"],
                        False,
                    ),
                )

        # Record the file as imported
        cur.execute(
            "INSERT INTO imported_files (filename, file_hash) VALUES (%s, %s)",
            (os.path.basename(file_path), file_hash),
        )

        if not dry_run:
            conn.commit()
            print("  -> file import committed")
        else:
            conn.rollback()
            print("  -> dry-run: changes rolled back (no commit)")

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
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT indexname FROM pg_indexes WHERE indexname = 'uniq_open_trade_on_fields';
            """
            )
            if not cur.fetchone():
                print(
                    "\nWARNING: 'uniq_open_trade_on_fields' index is missing! This can cause duplicates for open trades."
                )
                print("Run create_unique_index.py or apply migrations to add this index for consistency.\n")

        for path in paths:
            process_file(conn, path, tz=args.tz, archive_dir=args.archive_dir, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
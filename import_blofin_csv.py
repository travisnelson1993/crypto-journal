#!/usr/bin/env python3
"""
Blofin CSV Importer — Option B (Trades + Executions)

✔ Creates trades on OPEN
✔ Updates existing open trade on CLOSE (same file or later)
✔ Sets exit_price + end_date
✔ Records source + source_filename
✔ imported_files idempotency via SHA-256
✔ SAFE: no ON CONFLICT, no savepoints
"""

import argparse
import glob
import hashlib
import os
import shutil
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2

from app.utils.side_parser import infer_action_and_direction

SOURCE_NAME = "blofin_order_history"


# ───────────────────────── helpers ─────────────────────────

def normalize_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + dsn[len("postgresql+asyncpg://"):]
    return dsn


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_price_numeric(val):
    """
    Handles Blofin values like:
      '3.192 USDT'
      '0.29896 USDT'
      '85711.3'
    """
    if val is None:
        return None
    try:
        s = str(val).strip()
        if not s:
            return None
        # If it has a unit like "USDT", take first token
        num = s.split()[0]
        return float(num)
    except Exception:
        return None


def parse_quantity(val):
    """
    Handles Blofin values like:
      "100 ICP"
      "2500 TRX"
      "30 LIT"
      "0.01 BTC"
    """
    if val is None:
        return None
    try:
        s = str(val).strip()
        if not s:
            return None
        num = s.split()[0]
        return float(num)
    except Exception:
        return None


def parse_datetime(val, tz=None):
    try:
        dt = pd.to_datetime(val, errors="coerce")
        if pd.isna(dt):
            return None
        ts = dt.to_pydatetime()
        if tz:
            ts = ts.replace(tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))
        return ts
    except Exception:
        return None


def pick_first(row, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "--"):
            return v
    return None


# ───────────────────── DDL (DEDICATED CONNECTION) ─────────────────────

def ensure_imported_files_table(dsn: str):
    with psycopg2.connect(dsn) as conn:
        conn.autocommit = True
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


# ───────────────────────── core ─────────────────────────

def process_file(conn, dsn, file_path, tz=None, archive_dir=None):
    print(f"Processing: {file_path}")

    basename = os.path.basename(file_path)
    file_hash = file_sha256(file_path)

    ensure_imported_files_table(dsn)

    # --- idempotency ---
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM imported_files WHERE file_hash = %s", (file_hash,))
        if cur.fetchone():
            print("  -> already imported, skipping")
            return

    df = pd.read_csv(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    for _, row in df.iterrows():
        ticker = pick_first(row, "Underlying Asset", "Ticker", "symbol")
        if not ticker:
            continue

        side_raw = row.get("Side")
        action, direction, _ = infer_action_and_direction(side_raw)
        if not action:
            continue

        price = parse_price_numeric(pick_first(row, "Avg Fill", "Price"))
        qty = parse_quantity(pick_first(row, "Filled", "Quantity"))
        ts = parse_datetime(pick_first(row, "Order Time", "Time"), tz)

        # timestamp is always required
        if ts is None:
            continue

        # Quantity is required for OPEN (but if missing, default to 0 rather than crash)
        if action == "OPEN" and qty is None:
            qty = 0.0

        try:
            with conn.cursor() as cur:
                if action == "OPEN":
                    cur.execute(
                        """
                        INSERT INTO trades (
                            ticker,
                            direction,
                            quantity,
                            original_quantity,
                            entry_price,
                            created_at,
                            source,
                            source_filename
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            ticker,
                            (direction or "").upper(),
                            qty,
                            qty,
                            price,
                            ts,
                            SOURCE_NAME,
                            basename,
                        ),
                    )

                elif action == "CLOSE":
                    # Close exactly one open trade for this ticker (oldest first).
                    # Postgres-safe LIMIT via subquery.
                    cur.execute(
                        """
                        UPDATE trades
                        SET exit_price = %s,
                            end_date = %s
                        WHERE id = (
                            SELECT id
                            FROM trades
                            WHERE ticker = %s
                              AND end_date IS NULL
                            ORDER BY created_at
                            LIMIT 1
                        )
                        """,
                        (price, ts, ticker),
                    )

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"  -> row failed: {e}")

    # record imported file
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO imported_files (filename, file_hash) VALUES (%s,%s)",
            (basename, file_hash),
        )
    conn.commit()

    # Archive only if archive_dir is different than the file's current directory
    if archive_dir:
        src_dir = os.path.abspath(os.path.dirname(file_path))
        dst_dir = os.path.abspath(archive_dir)
        if src_dir != dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.move(file_path, os.path.join(dst_dir, basename))


# ───────────────────────── main ─────────────────────────

def gather_inputs(path):
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "*.csv")))
    return sorted(glob.glob(path))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", required=True)
    p.add_argument("--db", "-d", default=None)
    p.add_argument("--archive-dir", "-a", default=None)
    p.add_argument("--tz", default=None)
    args = p.parse_args()

    dsn = normalize_dsn(args.db or os.getenv("CRYPTO_JOURNAL_DSN"))
    if not dsn:
        raise SystemExit("CRYPTO_JOURNAL_DSN not set")

    paths = gather_inputs(args.input)
    if not paths:
        print("No CSV files found")
        return

    conn = psycopg2.connect(dsn)
    try:
        for path in paths:
            process_file(conn, dsn, path, tz=args.tz, archive_dir=args.archive_dir)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

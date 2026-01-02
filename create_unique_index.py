#!/usr/bin/env python3
"""
Check for duplicate 'open' trades and create the unique partial index:

  uniq_open_trade_on_fields ON trades (ticker, direction, entry_date, entry_price) WHERE end_date IS NULL

Usage:
  # Basic: check duplicates and create index if none
  python create_unique_index.py

  # Create a backup table first (recommended)
  python create_unique_index.py --backup

  # If you cannot use CONCURRENTLY in your environment, pass --no-concurrent
  python create_unique_index.py --no-concurrent

Notes:
  - The script reads the DB DSN from the CRYPTO_JOURNAL_DSN environment variable.
  - Example DSN (PowerShell):
    $env:CRYPTO_JOURNAL_DSN = "dbname=crypto_journal user=postgres password=YOURPASS host=127.0.0.1 port=5432"
"""
import argparse
import os
import sys

import psycopg2

INDEX_NAME = "uniq_open_trade_on_fields"
INDEX_SQL = f"""
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
ON trades (ticker, direction, entry_date, entry_price)
WHERE end_date IS NULL;
"""
INDEX_SQL_NOT_CONCURRENT = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
ON trades (ticker, direction, entry_date, entry_price)
WHERE end_date IS NULL;
"""

DUP_QUERY = """
SELECT ticker, direction, entry_date, entry_price, count(*) AS cnt
FROM trades
WHERE end_date IS NULL
GROUP BY ticker, direction, entry_date, entry_price
HAVING count(*) > 1
ORDER BY cnt DESC
LIMIT 200;
"""

DUP_DETAILS_SQL = """
WITH dup_keys AS (
  SELECT ticker, direction, entry_date, entry_price
  FROM trades
  WHERE end_date IS NULL
  GROUP BY ticker, direction, entry_date, entry_price
  HAVING count(*) > 1
)
SELECT t.id, t.ticker, t.direction, t.entry_date, t.entry_price, t.end_date
FROM trades t
JOIN dup_keys d USING (ticker, direction, entry_date, entry_price)
ORDER BY t.ticker, t.entry_date, t.id
LIMIT 200;
"""

BACKUP_SQL = "CREATE TABLE IF NOT EXISTS trades_backup AS TABLE trades WITH DATA;"


def get_dsn():
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        print(
            "CRYPTO_JOURNAL_DSN environment variable is not set. Please set it and re-run."
        )
        print("Example (PowerShell):")
        print(
            '$env:CRYPTO_JOURNAL_DSN = "dbname=crypto_journal user=postgres password=YOURPASS host=127.0.0.1 port=5432"'
        )
        sys.exit(1)
    return dsn


def check_duplicates(conn):
    with conn.cursor() as cur:
        cur.execute(DUP_QUERY)
        rows = cur.fetchall()
        return rows


def show_duplicate_details(conn):
    with conn.cursor() as cur:
        cur.execute(DUP_DETAILS_SQL)
        rows = cur.fetchall()
        return rows


def create_backup(conn):
    with conn.cursor() as cur:
        print("Creating trades_backup table (may take time)...")
        cur.execute(BACKUP_SQL)
    conn.commit()
    print("Backup created (trades_backup).")


def create_index(conn, concurrent=True):
    # CREATE INDEX CONCURRENTLY must be run with autocommit = True
    if concurrent:
        conn.autocommit = True
        sql = INDEX_SQL
    else:
        conn.autocommit = False
        sql = INDEX_SQL_NOT_CONCURRENT
    with conn.cursor() as cur:
        print("Creating unique index (this may take a while)...")
        cur.execute(sql)
    # If we set autocommit True it is already committed; if not, commit now
    if not concurrent:
        conn.commit()
    print("Index created (or already existed).")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--backup",
        action="store_true",
        help="Create trades_backup before making changes",
    )
    p.add_argument(
        "--no-concurrent",
        action="store_true",
        help="Create index without CONCURRENTLY (may take locks)",
    )
    args = p.parse_args()

    dsn = get_dsn()
    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        print("Failed to connect to DB:", e)
        sys.exit(1)

    try:
        dup = check_duplicates(conn)
        if dup:
            print(
                "Found duplicate open-trade keys that will prevent creating the unique index."
            )
            print(
                "Sample duplicates (ticker, direction, entry_date, entry_price, count):"
            )
            for r in dup:
                print(r)
            print(
                "\nDetailed rows (id, ticker, direction, entry_date, entry_price, end_date):"
            )
            details = show_duplicate_details(conn)
            for d in details:
                print(d)
            print("\nYou must deduplicate these rows before creating the unique index.")
            print("Recommended steps:")
            print(" 1) Create a backup (you can use --backup with this script).")
            print(
                " 2) Inspect and dedupe manually or use a SQL delete that keeps one row per key."
            )
            print(
                "\nExample SQL to keep the lowest id for each duplicate key (RUN ONLY AFTER BACKUP):"
            )
            print(
                """
WITH to_keep AS (
  SELECT min(id) AS keep_id
  FROM trades
  WHERE end_date IS NULL
  GROUP BY ticker, direction, entry_date, entry_price
  HAVING count(*) > 1
)
DELETE FROM trades
WHERE id IN (
  SELECT t.id
  FROM trades t
  LEFT JOIN to_keep k ON t.id = k.keep_id
  WHERE t.end_date IS NULL AND k.keep_id IS NULL
    AND (t.ticker, t.direction, t.entry_date, t.entry_price) IN (
      SELECT ticker, direction, entry_date, entry_price
      FROM trades
      WHERE end_date IS NULL
      GROUP BY ticker, direction, entry_date, entry_price
      HAVING count(*) > 1
    )
);
"""
            )
            sys.exit(2)

        # No duplicates found
        print("No duplicate open trades found. Safe to create the unique index.")
        if args.backup:
            create_backup(conn)
        create_index(conn, concurrent=not args.no_concurrent)

    finally:
        conn.close()


if __name__ == "__main__":
    main()

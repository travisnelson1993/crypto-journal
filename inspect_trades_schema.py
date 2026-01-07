#!/usr/bin/env python3
"""
Inspect trades table schema, constraints, and indexes.

Usage:
  Ensure CRYPTO_JOURNAL_DSN is set in the PowerShell session, then run:
    python inspect_trades_schema.py
"""
import os
import sys

import psycopg2


def get_dsn():
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        print("CRYPTO_JOURNAL_DSN not set. Set it and re-run.")
        sys.exit(1)
    return dsn


def run_query(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def main():
    dsn = get_dsn()
    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        print("Failed to connect:", e)
        sys.exit(1)

    try:
        print("1) trades table columns (information_schema.columns):")
        cols = run_query(
            conn,
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'trades'
            ORDER BY ordinal_position;
        """,
        )
        if not cols:
            print("  -> No table named 'trades' found in this database/schema.")
        else:
            for c in cols:
                print("  ", c)

        print("\n2) Table constraints (pg_constraint):")
        cons = run_query(
            conn,
            """
            SELECT conname, contype, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'trades'::regclass;
        """,
        )
        if cons:
            for c in cons:
                print("  ", c)
        else:
            print("  -> No constraints found (or table not present).")

        print("\n3) Indexes on trades (pg_indexes):")
        idxs = run_query(
            conn,
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'trades'
            ORDER BY indexname;
        """,
        )
        if idxs:
            for i in idxs:
                print("  ", i[0])
                print("    ", i[1])
        else:
            print("  -> No indexes found (or table not present).")

        print("\n4) Quick check: count of rows with end_date IS NULL (open trades):")
        cnt = run_query(conn, "SELECT count(*) FROM trades WHERE end_date IS NULL;")
        print("  ->", cnt[0][0])

        print(
            "\n5) Check for duplicates on (ticker, direction, entry_date, entry_price) among open trades:"
        )
        dups = run_query(
            conn,
            """
            SELECT ticker, direction, entry_date, entry_price, count(*) AS cnt
            FROM trades
            WHERE end_date IS NULL
            GROUP BY ticker, direction, entry_date, entry_price
            HAVING count(*) > 1
            ORDER BY cnt DESC
            LIMIT 50;
        """,
        )
        if dups:
            print("  -> Found duplicates (showing up to 50):")
            for d in dups:
                print("    ", d)
        else:
            print("  -> No duplicates found for the ON CONFLICT key among open trades.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

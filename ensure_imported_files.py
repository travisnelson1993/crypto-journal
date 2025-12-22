#!/usr/bin/env python3
"""
Helper script to ensure the imported_files table exists in the database.

Usage:
  python ensure_imported_files.py

Requires CRYPTO_JOURNAL_DSN environment variable to be set.
"""
import os
import sys
import psycopg2


def ensure_imported_files_table(dsn):
    """Ensure the imported_files table exists."""
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
        print("✓ imported_files table ensured")
    except Exception as e:
        print(f"✗ Error creating table: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        print("ERROR: CRYPTO_JOURNAL_DSN environment variable not set")
        sys.exit(1)
    
    ensure_imported_files_table(dsn)
    print("Done.")


if __name__ == "__main__":
    main()

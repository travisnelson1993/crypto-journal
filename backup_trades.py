#!/usr/bin/env python3
"""
Helper script to backup the trades table to a new table.

Usage:
  python backup_trades.py [--backup-name trades_backup]

Creates a copy of the trades table with timestamp for safe keeping.
Requires CRYPTO_JOURNAL_DSN environment variable to be set.
"""
import argparse
import os
import sys
from datetime import datetime
import psycopg2


def backup_trades(dsn, backup_name=None):
    """Create a backup of the trades table."""
    if backup_name is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"trades_backup_{timestamp}"
    
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        
        # Check if trades table exists
        cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'trades'
        );
        """)
        if not cur.fetchone()[0]:
            print("✗ trades table does not exist")
            sys.exit(1)
        
        # Check if backup already exists
        cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = %s
        );
        """, (backup_name,))
        if cur.fetchone()[0]:
            print(f"✗ Backup table '{backup_name}' already exists")
            sys.exit(1)
        
        # Get count of rows in trades
        cur.execute("SELECT COUNT(*) FROM trades")
        count = cur.fetchone()[0]
        
        print(f"Creating backup of {count} trades...")
        
        # Create backup table
        cur.execute(f"CREATE TABLE {backup_name} AS SELECT * FROM trades")
        conn.commit()
        
        # Verify backup
        cur.execute(f"SELECT COUNT(*) FROM {backup_name}")
        backup_count = cur.fetchone()[0]
        
        if backup_count == count:
            print(f"✓ Backup created successfully: {backup_name}")
            print(f"  Rows backed up: {backup_count}")
        else:
            print(f"✗ Warning: Row count mismatch!")
            print(f"  Original: {count}, Backup: {backup_count}")
        
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"✗ Error creating backup: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backup trades table")
    parser.add_argument("--backup-name", help="Name for backup table (default: trades_backup_TIMESTAMP)")
    args = parser.parse_args()
    
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        print("ERROR: CRYPTO_JOURNAL_DSN environment variable not set")
        sys.exit(1)
    
    backup_trades(dsn, args.backup_name)


if __name__ == "__main__":
    main()

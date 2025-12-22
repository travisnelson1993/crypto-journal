#!/usr/bin/env python3
"""
Helper script to verify imports by showing recent trades and statistics.

Usage:
  python verify_import.py [--limit 10]

Shows recent imports and statistics from the trades table.
Requires CRYPTO_JOURNAL_DSN environment variable to be set.
"""
import argparse
import os
import sys
import psycopg2


def verify_import(dsn, limit=10):
    """Verify imports by showing recent trades and statistics."""
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
        
        # Get total count
        cur.execute("SELECT COUNT(*) FROM trades")
        total_count = cur.fetchone()[0]
        print(f"Total trades in database: {total_count}")
        
        # Get count by source
        cur.execute("""
        SELECT source, COUNT(*) 
        FROM trades 
        GROUP BY source 
        ORDER BY COUNT(*) DESC
        """)
        print("\nTrades by source:")
        for source, count in cur.fetchall():
            source_name = source if source else "(null)"
            print(f"  {source_name}: {count}")
        
        # Get count of open vs closed
        cur.execute("""
        SELECT 
            COUNT(CASE WHEN end_date IS NULL THEN 1 END) as open_trades,
            COUNT(CASE WHEN end_date IS NOT NULL THEN 1 END) as closed_trades
        FROM trades
        """)
        open_count, closed_count = cur.fetchone()
        print(f"\nOpen trades: {open_count}")
        print(f"Closed trades: {closed_count}")
        
        # Get recent trades
        cur.execute("""
        SELECT id, ticker, direction, entry_price, entry_date, entry_summary, created_at
        FROM trades 
        ORDER BY created_at DESC 
        LIMIT %s
        """, (limit,))
        
        print(f"\nMost recent {limit} trades:")
        print("-" * 100)
        for row in cur.fetchall():
            id, ticker, direction, entry_price, entry_date, entry_summary, created_at = row
            direction_str = direction if direction else "N/A"
            entry_price_str = f"${entry_price:.2f}" if entry_price else "N/A"
            print(f"ID {id}: {ticker} {direction_str} @ {entry_price_str}")
            print(f"  Entry date: {entry_date}")
            print(f"  Summary: {entry_summary}")
            print(f"  Created: {created_at}")
            print()
        
        cur.close()
    except Exception as e:
        print(f"✗ Error querying database: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Verify imports")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent trades to show (default: 10)")
    args = parser.parse_args()
    
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        print("ERROR: CRYPTO_JOURNAL_DSN environment variable not set")
        sys.exit(1)
    
    verify_import(dsn, args.limit)


if __name__ == "__main__":
    main()

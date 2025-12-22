#!/usr/bin/env python3
"""
Helper script to check the imported_files table and list all imported files.

Usage:
  python check_imported_files.py

Requires CRYPTO_JOURNAL_DSN environment variable to be set.
"""
import os
import sys
import psycopg2


def check_imported_files(dsn):
    """Check and list all imported files."""
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        
        # Check if table exists
        cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'imported_files'
        );
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("✗ imported_files table does not exist")
            print("  Run: python ensure_imported_files.py")
            sys.exit(1)
        
        print("✓ imported_files table exists")
        
        # Get count
        cur.execute("SELECT COUNT(*) FROM imported_files")
        count = cur.fetchone()[0]
        print(f"\nTotal files imported: {count}")
        
        if count > 0:
            # List all files
            cur.execute("""
            SELECT id, filename, file_hash, imported_at 
            FROM imported_files 
            ORDER BY imported_at DESC
            """)
            
            print("\nImported files:")
            print("-" * 80)
            for row in cur.fetchall():
                id, filename, file_hash, imported_at = row
                print(f"ID: {id}")
                print(f"  Filename: {filename}")
                print(f"  Hash: {file_hash[:16]}...")
                print(f"  Imported at: {imported_at}")
                print()
        
        cur.close()
    except Exception as e:
        print(f"✗ Error querying database: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        print("ERROR: CRYPTO_JOURNAL_DSN environment variable not set")
        sys.exit(1)
    
    check_imported_files(dsn)


if __name__ == "__main__":
    main()

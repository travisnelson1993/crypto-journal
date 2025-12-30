"""
Regression test: import a CSV file containing both an open and its close.

Verifies that the importer:
1. Updates the open trade with close information (end_date, exit_price)
2. Inserts a separate row for the close CSV row (preserves audit trail)
3. Maintains one DB row per CSV row for idempotency

This test uses the existing sample_order_history.csv fixture which contains:
- Row 1: Open Long BTCUSDT at 85711.3
- Row 2: Close Long BTCUSDT at 87518.4  
- Row 3: Open Long ARCUSDT at 0.04565
"""
import os
import sys
import shutil
import subprocess
import uuid
import psycopg2
import pandas as pd
import pytest

SOURCE_NAME = "blofin_order_history"


def get_conn(dsn):
    return psycopg2.connect(dsn)


@pytest.fixture
def dsn():
    d = os.environ.get("CRYPTO_JOURNAL_DSN")
    if not d:
        pytest.skip("CRYPTO_JOURNAL_DSN not set; skipping integration test")
    return d


def cleanup_db(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trades WHERE source = %s", (SOURCE_NAME,))
        cur.execute("DELETE FROM imported_files WHERE filename LIKE %s", ("test-close-same-file-%",))
    conn.commit()


def run_importer(file_path, dsn):
    env = os.environ.copy()
    subprocess.check_call(
        [sys.executable, "import_blofin_csv.py", "--input", str(file_path), "--db", dsn],
        env=env,
    )


def test_import_close_in_same_file(tmp_path, dsn):
    """
    Test that importing a file with both open and close rows:
    - Updates the open trade with close info
    - Inserts a separate close row (audit trail)
    - Results in one DB row per CSV row
    """
    conn = get_conn(dsn)
    cleanup_db(conn)

    # Use existing fixture with open + close for BTCUSDT
    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(fixture), f"Fixture not found: {fixture}"

    # Create temp copy with unique name
    test_file = tmp_path / f"test-close-same-file-{uuid.uuid4().hex[:8]}.csv"
    shutil.copy(fixture, test_file)

    # Count CSV rows (excluding header)
    df = pd.read_csv(fixture, dtype=str)
    csv_row_count = len(df)
    
    # Expected: 1 open BTC, 1 close BTC, 1 open ARC = 3 rows
    assert csv_row_count == 3, f"Expected 3 CSV rows in fixture, got {csv_row_count}"

    # Run importer
    run_importer(test_file, dsn)

    # Reconnect to get fresh view
    conn = get_conn(dsn)

    with conn.cursor() as cur:
        # Verify total row count matches CSV row count (one DB row per CSV row)
        cur.execute("SELECT count(*) FROM trades WHERE source = %s", (SOURCE_NAME,))
        total_rows = cur.fetchone()[0]
        assert total_rows == csv_row_count, f"Expected {csv_row_count} total DB rows, got {total_rows}"

        # Check BTCUSDT open trade was updated with close info
        cur.execute("""
            SELECT id, ticker, direction, entry_price, exit_price, entry_date, end_date, entry_summary
            FROM trades
            WHERE source = %s
              AND ticker = 'BTCUSDT'
              AND direction = 'LONG'
              AND entry_summary LIKE '%Open%'
            ORDER BY entry_date
        """, (SOURCE_NAME,))
        open_trades = cur.fetchall()
        
        assert len(open_trades) == 1, f"Expected 1 open BTCUSDT trade, got {len(open_trades)}"
        open_trade = open_trades[0]
        
        # Verify the open trade has been updated with close information
        assert open_trade[4] is not None, "Open trade exit_price should be set"
        assert open_trade[6] is not None, "Open trade end_date should be set"
        assert abs(open_trade[4] - 87518.4) < 0.01, f"Expected exit_price ~87518.4, got {open_trade[4]}"

        # Check that a separate close row was inserted (audit trail)
        cur.execute("""
            SELECT id, ticker, direction, entry_price, exit_price, entry_date, end_date, entry_summary
            FROM trades
            WHERE source = %s
              AND ticker = 'BTCUSDT'
              AND direction = 'LONG'
              AND entry_summary LIKE '%Close%'
            ORDER BY entry_date
        """, (SOURCE_NAME,))
        close_trades = cur.fetchall()
        
        assert len(close_trades) == 1, f"Expected 1 close BTCUSDT row, got {len(close_trades)}"
        close_trade = close_trades[0]
        
        # Verify the close trade row has correct values
        assert close_trade[4] is not None, "Close trade exit_price should be set"
        assert close_trade[6] is not None, "Close trade end_date should be set"
        assert abs(close_trade[4] - 87518.4) < 0.01, f"Expected close exit_price ~87518.4, got {close_trade[4]}"

        # Verify ARCUSDT open trade exists (should not be affected)
        cur.execute("""
            SELECT count(*)
            FROM trades
            WHERE source = %s
              AND ticker = 'ARCUSDT'
              AND direction = 'LONG'
              AND end_date IS NULL
        """, (SOURCE_NAME,))
        arc_count = cur.fetchone()[0]
        assert arc_count == 1, f"Expected 1 open ARCUSDT trade, got {arc_count}"

    cleanup_db(conn)
    conn.close()

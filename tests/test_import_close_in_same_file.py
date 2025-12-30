"""
Regression test for Blofin CSV importer close application logic.

Tests that when a CSV contains both an open and its close:
1. The open trade is inserted
2. The close updates the open trade (sets end_date)
3. The close CSV row is also inserted as a separate DB row (one DB row per CSV row)
"""
import os
import sys
import shutil
import subprocess
import uuid
import psycopg2
import hashlib
import pandas as pd
import pytest

SOURCE_NAME = "blofin_order_history"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


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
        cur.execute("DELETE FROM imported_files WHERE filename LIKE %s", ("test-sample-%",))
    conn.commit()


def run_importer(file_path, dsn):
    env = os.environ.copy()
    subprocess.check_call(
        [sys.executable, "import_blofin_csv.py", "--input", str(file_path), "--db", dsn, "--archive-dir", str(os.path.dirname(file_path))],
        env=env,
    )


def test_importer_applies_close_and_inserts_close_row(tmp_path, dsn):
    """
    Test that when importing a file with both open and close:
    1. Open trade is inserted
    2. Close updates the open trade (sets end_date, exit_price)
    3. Close CSV row is also inserted as a separate row (one DB row per CSV row)
    """
    conn = get_conn(dsn)
    cleanup_db(conn)

    # Use fixture with open and close in same file
    fixture = os.path.join("tests", "fixtures", "open_and_close_same_file.csv")
    assert os.path.exists(fixture), f"Fixture not found: {fixture}"

    in1 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-openclose.csv"
    shutil.copy(fixture, in1)

    # Expected: 2 CSV rows (1 open + 1 close)
    df = pd.read_csv(fixture, dtype=str)
    expected_csv_rows = len(df)
    assert expected_csv_rows == 2, "Fixture should have exactly 2 rows (1 open + 1 close)"

    # Run importer
    run_importer(in1, dsn)

    # Verify results
    conn = get_conn(dsn)
    with conn.cursor() as cur:
        # Count total trades
        cur.execute("SELECT count(*) FROM trades WHERE source = %s", (SOURCE_NAME,))
        total_count = cur.fetchone()[0]
        
        # Expected: 3 rows total
        # - 1 open trade (with end_date set after close is applied)
        # - 1 close row (inserted for the close CSV row)
        # Actually, wait - let me re-read the spec. It says:
        # "Always INSERT a trade row representing the close CSV row so there is one DB row per CSV row"
        # So we expect: 1 open + 1 close = 2 rows matching CSV rows
        # But the open row should have end_date set because the close updated it
        
        # Let's verify:
        # 1. One row with end_date IS NULL initially becomes end_date IS NOT NULL (the open that was updated)
        # 2. One row representing the close CSV row
        # Total: We should see 2 DB rows, one of which is the "open" and one is the "close"
        
        assert total_count == 2, f"Expected 2 DB rows (one per CSV row), got {total_count}"
        
        # Get the open trade (should have end_date set after close application)
        cur.execute("""
        SELECT id, ticker, direction, entry_price, exit_price, end_date, entry_summary
        FROM trades
        WHERE source = %s AND entry_summary LIKE %s
        ORDER BY entry_date, id
        """, (SOURCE_NAME, "%Imported: Open%"))
        open_rows = cur.fetchall()
        assert len(open_rows) == 1, f"Expected 1 open trade row, got {len(open_rows)}"
        
        open_id, ticker, direction, entry_price, exit_price, end_date, entry_summary = open_rows[0]
        assert ticker == "ETHUSDT"
        assert direction == "LONG"
        assert entry_price is not None
        # After close is applied, the open trade should have end_date and exit_price set
        assert end_date is not None, "Open trade should have end_date set after close is applied"
        assert exit_price is not None, "Open trade should have exit_price set after close is applied"
        
        # Get the close row (representing the close CSV row)
        cur.execute("""
        SELECT id, ticker, direction, entry_price, exit_price, end_date, entry_summary
        FROM trades
        WHERE source = %s AND entry_summary LIKE %s
        ORDER BY entry_date, id
        """, (SOURCE_NAME, "%close%"))
        close_rows = cur.fetchall()
        assert len(close_rows) == 1, f"Expected 1 close trade row, got {len(close_rows)}"
        
        close_id, ticker, direction, entry_price, exit_price, end_date, entry_summary = close_rows[0]
        assert ticker == "ETHUSDT"
        assert direction == "LONG"
        assert end_date is not None, "Close trade should have end_date set"
        assert exit_price is not None, "Close trade should have exit_price set"

    cleanup_db(conn)
    conn.close()

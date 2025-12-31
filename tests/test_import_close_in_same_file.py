import os
import shutil
import uuid
import subprocess
import sys
import psycopg2


def test_close_in_same_file_applies_update(tmp_path):
    """
    Self-contained regression test that:
      - clears previous imports from this source,
      - copies the sample fixture to a temp file,
      - runs import_blofin_csv.py on that file,
      - verifies the BTCUSDT open was updated with the close from the same file.
    """
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    assert dsn, "CRYPTO_JOURNAL_DSN environment variable must be set for this test"

    # Clean up any prior rows for this source so test is deterministic
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM trades WHERE source = %s", ("blofin_order_history",))
            cur.execute("DELETE FROM imported_files WHERE filename LIKE %s", ("test-sample-%",))
        conn.commit()
    finally:
        conn.close()

    # Copy fixture to a temp file in tmp_path
    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(fixture), f"Fixture not found: {fixture}"
    in_file = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}.csv"
    shutil.copy(fixture, in_file)

    # Run importer as a subprocess, using the same python interpreter and env DSN
    env = os.environ.copy()
    env["CRYPTO_JOURNAL_DSN"] = dsn
    proc = subprocess.run(
        [sys.executable, "import_blofin_csv.py", "--input", str(in_file)],
        cwd=os.getcwd(), env=env, capture_output=True, text=True
    )

    # Print stdout/stderr for debugging in pytest -s mode
    print(proc.stdout)
    print(proc.stderr)
    assert proc.returncode == 0, f"Importer failed (returncode={proc.returncode}); stderr:\n{proc.stderr}"

    # Verify the close was applied to the matching open trade
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT exit_price, end_date FROM trades WHERE ticker = %s AND entry_price = %s ORDER BY created_at DESC LIMIT 1",
                ("BTCUSDT", 85711.3),
            )
            row = cur.fetchone()
            assert row is not None, "Expected a trade row for BTCUSDT to exist"
            exit_price, end_date = row
            assert exit_price == 87518.4, f"expected exit_price 87518.4 but got {exit_price}"
            assert end_date is not None, "expected end_date to be set for closed trade"
    finally:
        conn.close()
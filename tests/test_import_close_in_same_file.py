import os
import shutil
import subprocess
import sys
import uuid
from decimal import Decimal

import psycopg2
import pytest


def _has_column(conn, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            LIMIT 1
            """,
            (table, column),
        )
        return cur.fetchone() is not None


def test_close_in_same_file_applies_update(tmp_path):
    """
    Regression test:
      - clears previous imports,
      - imports a file containing open + close,
      - verifies the open trade was updated (closed).
    """
    dsn = os.getenv("CRYPTO_JOURNAL_DSN")
    if not dsn:
        pytest.skip("CRYPTO_JOURNAL_DSN environment variable must be set")

    # --- Clean DB ---
    conn = psycopg2.connect(dsn)
    try:
        has_source = _has_column(conn, "trades", "source")
        with conn.cursor() as cur:
            if has_source:
                cur.execute(
                    "DELETE FROM trades WHERE source = %s",
                    ("blofin_order_history",),
                )
            else:
                # Fallback: only delete BTCUSDT if no source column exists
                cur.execute("DELETE FROM trades WHERE ticker = %s", ("BTCUSDT",))

            # imported_files table is part of importer idempotency
            cur.execute("DELETE FROM imported_files")
        conn.commit()
    finally:
        conn.close()

    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(fixture)

    in_file = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}.csv"
    shutil.copy(fixture, in_file)

    env = os.environ.copy()
    env["CRYPTO_JOURNAL_DSN"] = dsn

    proc = subprocess.run(
        [sys.executable, "import_blofin_csv.py", "--input", str(in_file)],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    print(proc.stdout)
    print(proc.stderr)
    assert proc.returncode == 0

    # --- Verify CLOSED trade exists ---
    conn = psycopg2.connect(dsn)
    try:
        has_source = _has_column(conn, "trades", "source")
        with conn.cursor() as cur:
            if has_source:
                cur.execute(
                    """
                    SELECT exit_price, end_date
                    FROM trades
                    WHERE ticker = %s
                      AND source = %s
                      AND end_date IS NOT NULL
                    """,
                    ("BTCUSDT", "blofin_order_history"),
                )
            else:
                cur.execute(
                    """
                    SELECT exit_price, end_date
                    FROM trades
                    WHERE ticker = %s
                      AND end_date IS NOT NULL
                    """,
                    ("BTCUSDT",),
                )

            row = cur.fetchone()
            assert row is not None, "Expected a closed BTCUSDT trade"

            exit_price, end_date = row

            # psycopg2 may return Decimal for NUMERIC
            assert Decimal(str(exit_price)) == Decimal("87518.4")
            assert end_date is not None
    finally:
        conn.close()


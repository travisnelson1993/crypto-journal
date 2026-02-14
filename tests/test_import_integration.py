import hashlib
import os
import shutil
import subprocess
import sys
import uuid

import pandas as pd
import psycopg2
import pytest

SOURCE_NAME = "blofin_order_history"


# ---------- helpers ----------

def get_conn(dsn):
    return psycopg2.connect(dsn)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def cleanup_db(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trades WHERE source = %s", (SOURCE_NAME,))
        cur.execute("DELETE FROM imported_files")
    conn.commit()


def ensure_unique_open_trade_index(conn):
    """
    Enforce: only ONE open trade per (ticker, direction, entry_price).
    Uses created_at instead of non-existent entry_date.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
            ON trades (ticker, direction, entry_price)
            WHERE end_date IS NULL;
            """
        )
    conn.commit()


def run_importer(file_path, dsn):
    subprocess.check_call(
        [
            sys.executable,
            "import_blofin_csv.py",
            "--input",
            str(file_path),
            "--db",
            dsn,
            "--archive-dir",
            str(os.path.dirname(file_path)),
        ],
        env=os.environ.copy(),
    )


def count_trades(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM trades WHERE source = %s",
            (SOURCE_NAME,),
        )
        return cur.fetchone()[0]


def imported_file_count_by_hash(conn, file_hash):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM imported_files WHERE file_hash = %s",
            (file_hash,),
        )
        return cur.fetchone()[0]


def get_recent_source_filenames(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_filename
            FROM trades
            WHERE source = %s
            ORDER BY created_at DESC
            """,
            (SOURCE_NAME,),
        )
        return [r[0] for r in cur.fetchall()]


# ---------- fixtures ----------

@pytest.fixture
def dsn():
    d = os.environ.get("CRYPTO_JOURNAL_DSN")
    if not d:
        pytest.skip("CRYPTO_JOURNAL_DSN not set")
    return d


# ---------- test ----------

def test_importer_idempotent_and_records_filename(tmp_path, dsn):
    conn = get_conn(dsn)
    cleanup_db(conn)
    ensure_unique_open_trade_index(conn)
    conn.close()

    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(fixture)

    in1 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-a.csv"
    in2 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-b.csv"
    shutil.copy(fixture, in1)
    shutil.copy(fixture, in2)

    df = pd.read_csv(fixture, dtype=str)
    expected_rows = df["Side"].str.contains("Open", case=False, na=False).sum()

    # ---- First import ----
    run_importer(in1, dsn)

    conn = get_conn(dsn)
    assert count_trades(conn) == expected_rows

    h1 = file_sha256(in1)
    assert imported_file_count_by_hash(conn, h1) == 1

    filenames = get_recent_source_filenames(conn)
    assert os.path.basename(str(in1)) in filenames
    conn.close()

    # ---- Second import (same content, new name) ----
    run_importer(in2, dsn)

    conn = get_conn(dsn)
    assert count_trades(conn) == expected_rows  # idempotent
    assert imported_file_count_by_hash(conn, h1) == 1
    conn.close()

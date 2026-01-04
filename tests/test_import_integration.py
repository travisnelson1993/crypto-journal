import hashlib
import os
import shutil
import subprocess
import sys
import uuid

import pandas as pd
import psycopg2
import pytest

from alembic.config import Config
from alembic import command

SOURCE_NAME = "blofin_order_history"


# ---------- helpers ----------

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_conn(dsn):
    return psycopg2.connect(dsn)


def apply_migrations(dsn):
    # Force alembic + importer subprocess to use the SAME test DB
    os.environ["DATABASE_URL"] = dsn

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", dsn)
    command.upgrade(cfg, "head")



def cleanup_db(conn):
    """
    Remove rows created by this test so it is idempotent across runs.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trades WHERE source = %s", (SOURCE_NAME,))
        cur.execute(
            "DELETE FROM imported_files WHERE filename LIKE %s",
            ("test-sample-%",),
        )
    conn.commit()


def run_importer(file_path, dsn):
    """
    Run the importer using the same Python interpreter pytest is using.
    """
    env = os.environ.copy()
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
        env=env,
    )


def count_trades(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM trades WHERE source = %s", (SOURCE_NAME,))
        return cur.fetchone()[0]


def imported_file_count_by_hash(conn, file_hash):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM imported_files WHERE file_hash = %s",
            (file_hash,),
        )
        return cur.fetchone()[0]


def get_recent_source_filenames(conn, limit=100):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_filename
            FROM trades
            WHERE source = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (SOURCE_NAME, limit),
        )
        return [r[0] for r in cur.fetchall()]


# ---------- fixtures ----------

@pytest.fixture
def dsn():
    d = os.environ.get("CRYPTO_JOURNAL_DSN")
    if not d:
        pytest.skip("CRYPTO_JOURNAL_DSN not set; skipping integration test")
    return d


# ---------- test ----------

def test_importer_idempotent_and_records_filename(tmp_path, dsn):
    # Ensure schema is fully migrated (tables + indexes)
    apply_migrations(dsn)

    # Clean database state for test
    conn = get_conn(dsn)
    cleanup_db(conn)

    # Prepare two input files with identical content but different names
    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(
        fixture
    ), "Fixture not found: tests/fixtures/sample_order_history.csv"

    in1 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-a.csv"
    in2 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-b.csv"
    shutil.copy(fixture, in1)
    shutil.copy(fixture, in2)

    # Expected rows = number of CSV rows (header excluded)
    df = pd.read_csv(fixture, dtype=str)
    expected_rows = len(df)

    # Run importer on first file
    run_importer(in1, dsn)

    # Verify rows inserted
    conn = get_conn(dsn)
    first_count = count_trades(conn)
    assert (
        first_count == expected_rows
    ), f"expected {expected_rows} rows after first import, got {first_count}"

    # Verify imported_files recorded exactly once
    h1 = file_sha256(in1)
    assert imported_file_count_by_hash(conn, h1) == 1

    # Verify source_filename is populated
    filenames = get_recent_source_filenames(conn)
    assert all(f is not None for f in filenames)
    assert os.path.basename(str(in1)) in filenames

    # Run importer again with identical contents but different filename
    run_importer(in2, dsn)

    # Row count should not change (idempotency)
    second_count = count_trades(conn)
    assert second_count == first_count

    # imported_files should still contain only one entry for that hash
    assert imported_file_count_by_hash(conn, h1) == 1

    # Cleanup so test is repeatable
    cleanup_db(conn)
    conn.close()

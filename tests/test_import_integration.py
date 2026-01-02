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
        cur.execute(
            "DELETE FROM imported_files WHERE filename LIKE %s", ("test-sample-%",)
        )
    conn.commit()


def run_importer(file_path, dsn):
    # Use the same Python interpreter pytest is running under
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
            "SELECT count(*) FROM imported_files WHERE file_hash = %s", (file_hash,)
        )
        return cur.fetchone()[0]


def get_recent_source_filenames(conn, limit=100):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_filename FROM trades WHERE source = %s ORDER BY created_at DESC LIMIT %s",
            (SOURCE_NAME, limit),
        )
        return [r[0] for r in cur.fetchall()]


def test_importer_idempotent_and_records_filename(tmp_path, dsn):
    # prepare DB
    conn = get_conn(dsn)
    cleanup_db(conn)

    # prepare two input files with identical content but different names
    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(
        fixture
    ), "Fixture not found: tests/fixtures/sample_order_history.csv"

    in1 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-a.csv"
    in2 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-b.csv"
    shutil.copy(fixture, in1)
    shutil.copy(fixture, in2)

    # expected rows = number of CSV rows (header excluded)
    df = pd.read_csv(fixture, dtype=str)
    expected_rows = len(df)

    # Run importer on first file
    run_importer(in1, dsn)

    # Verify rows inserted and source_filename present
    conn = get_conn(dsn)
    first_count = count_trades(conn)
    assert (
        first_count == expected_rows
    ), f"expected {expected_rows} rows after first import, got {first_count}"

    # Check imported_files entry for the file hash (should be 1)
    h1 = file_sha256(in1)
    assert imported_file_count_by_hash(conn, h1) == 1

    # Check trades have source_filename set (and at least one matches the basename we used)
    filenames = get_recent_source_filenames(conn)
    assert all(
        f is not None for f in filenames
    ), "Not all trades have source_filename populated"
    assert (
        os.path.basename(str(in1)) in filenames
    ), "source_filename not recorded as expected"

    # Run importer on second file (same contents, different name) -> should be skipped due to hash match
    run_importer(in2, dsn)

    # Count should remain the same
    second_count = count_trades(conn)
    assert (
        second_count == first_count
    ), "Importer was not idempotent; row count changed after re-run"

    # imported_files for that hash should still be 1 (no duplicate file_hash rows)
    assert imported_file_count_by_hash(conn, h1) == 1

    # cleanup DB (so test is idempotent across runs)
    cleanup_db(conn)
    conn.close()

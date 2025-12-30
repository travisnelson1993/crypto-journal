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


def get_recent_source_filenames(conn, limit=100):
    with conn.cursor() as cur:
        cur.execute("SELECT source_filename FROM trades WHERE source = %s ORDER BY created_at DESC LIMIT %s", (SOURCE_NAME, limit))
        return [r[0] for r in cur.fetchall()]


@pytest.mark.integration
def test_importer_records_source_filename(tmp_path, dsn):
    conn = get_conn(dsn)
    cleanup_db(conn)

    fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
    assert os.path.exists(fixture), f"Fixture not found: {fixture}"

    in1 = tmp_path / f"test-sample-{uuid.uuid4().hex[:8]}-a.csv"
    shutil.copy(fixture, in1)

    run_importer(in1, dsn)

    conn = get_conn(dsn)
    filenames = get_recent_source_filenames(conn)
    assert filenames, "No filenames found after import"
    assert all(f is not None for f in filenames), "Not all trades have source_filename populated"
    assert os.path.basename(str(in1)) in filenames, "source_filename not recorded as expected"

    cleanup_db(conn)
    conn.close()

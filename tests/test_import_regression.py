import hashlib
import os
import subprocess
import sys
import uuid

import psycopg2
import pytest

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


@pytest.fixture
def dsn():
    d = os.environ.get("CRYPTO_JOURNAL_DSN")
    if not d:
        pytest.skip("CRYPTO_JOURNAL_DSN not set; skipping integration test")
    return d


def cleanup_db(conn):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM trades WHERE source = %s",
            (SOURCE_NAME,),
        )
        cur.execute("DELETE FROM imported_files")
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
        ],
        env=os.environ.copy(),
    )


# ---------- test ----------

def test_importer_records_source_filename(tmp_path, dsn):
    conn = get_conn(dsn)
    try:
        cleanup_db(conn)

        fixture = os.path.join("tests", "fixtures", "sample_order_history.csv")
        assert os.path.exists(fixture)

        infile = tmp_path / f"sample-{uuid.uuid4().hex[:8]}.csv"
        with open(fixture, "rb") as src, open(infile, "wb") as dst:
            dst.write(src.read())

        run_importer(infile, dsn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trades
                WHERE source = %s
                  AND source_filename IS NOT NULL
                """,
                (SOURCE_NAME,),
            )
            count = cur.fetchone()[0]

        assert count > 0, "Expected trades to record source_filename"

    finally:
        conn.close()

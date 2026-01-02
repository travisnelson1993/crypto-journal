import os

import psycopg2

dsn = os.getenv("CRYPTO_JOURNAL_DSN")
if not dsn:
    raise SystemExit("CRYPTO_JOURNAL_DSN not set")
conn = psycopg2.connect(dsn)
with conn.cursor() as cur:
    cur.execute(
        "DROP TABLE IF EXISTS trades_backup; CREATE TABLE trades_backup AS TABLE trades WITH DATA;"
    )
conn.commit()
conn.close()
print("trades backed up to trades_backup")

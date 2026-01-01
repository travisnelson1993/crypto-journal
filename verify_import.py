import os

import psycopg2

dsn = os.getenv("CRYPTO_JOURNAL_DSN")
conn = psycopg2.connect(dsn)
with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM trades WHERE source='blofin_order_history';")
    print("rows from source:", cur.fetchone()[0])
conn.close()

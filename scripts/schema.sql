-- Schema synced with final Alembic migrations
-- This is the baseline DB used by CI before migrations run

CREATE TABLE IF NOT EXISTS trades (
  id SERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  direction TEXT,
  entry_price DOUBLE PRECISION,
  exit_price DOUBLE PRECISION,
  stop_loss DOUBLE PRECISION,
  leverage INTEGER NOT NULL DEFAULT 1,
  entry_date TIMESTAMP,
  end_date TIMESTAMP,
  entry_summary TEXT,
  orphan_close BOOLEAN NOT NULL DEFAULT false,
  source TEXT,
  created_at TIMESTAMP DEFAULT now(),
  source_filename TEXT,
  is_duplicate BOOLEAN NOT NULL DEFAULT false
);

DROP INDEX IF EXISTS uq_open_trade_key;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
  ON trades (ticker, direction, entry_date, entry_price)
  WHERE end_date IS NULL;

CREATE TABLE IF NOT EXISTS imported_files (
  id SERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  file_hash TEXT NOT NULL UNIQUE,
  imported_at TIMESTAMP DEFAULT now()
);

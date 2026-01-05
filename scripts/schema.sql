-- Schema synced with final Alembic migrations
-- This is the baseline DB used by CI before migrations run

CREATE TABLE IF NOT EXISTS trades (
  id SERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  direction VARCHAR(16),
  entry_price DOUBLE PRECISION,
  exit_price DOUBLE PRECISION,
  stop_loss DOUBLE PRECISION,
  leverage INTEGER NOT NULL DEFAULT 1,
  entry_date TIMESTAMPTZ,
  end_date TIMESTAMPTZ,
  entry_summary TEXT,
  orphan_close BOOLEAN NOT NULL DEFAULT FALSE,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_filename TEXT,
  is_duplicate BOOLEAN NOT NULL DEFAULT FALSE
);

-- Unique index for open trades (matches importer + tests)
CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
  ON trades (ticker, direction, entry_date, entry_price)
  WHERE end_date IS NULL;

CREATE TABLE IF NOT EXISTS imported_files (
  id SERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  file_hash TEXT NOT NULL UNIQUE,
  imported_at TIMESTAMPTZ DEFAULT now()
);

-- Minimal schema required by importer and integration test

CREATE TABLE IF NOT EXISTS trades (
  id SERIAL PRIMARY KEY,
  ticker TEXT,
  direction TEXT,
  entry_date TIMESTAMP,
  entry_price DOUBLE PRECISION,
  exit_price DOUBLE PRECISION,
  end_date TIMESTAMP,
  stop_loss DOUBLE PRECISION,
  leverage DOUBLE PRECISION DEFAULT 1.0,
  entry_summary TEXT,
  orphan_close BOOLEAN DEFAULT FALSE,
  source TEXT,
  source_filename TEXT,
  created_at TIMESTAMP DEFAULT now(),
  is_duplicate BOOLEAN DEFAULT FALSE
);

-- Prevent duplicate open trades with same key (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
  ON trades (ticker, direction, entry_date, entry_price)
  WHERE end_date IS NULL;

-- imported_files table (importer also ensures this table exists, but create here for CI init)
CREATE TABLE IF NOT EXISTS imported_files (
  id SERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  file_hash TEXT NOT NULL UNIQUE,
  imported_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

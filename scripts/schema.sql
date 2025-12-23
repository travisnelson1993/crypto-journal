-- Minimal schema required by importer and integration test

CREATE TABLE IF NOT EXISTS trades (
  id SERIAL PRIMARY KEY,
  ticker TEXT,
  direction TEXT,
  entry_date TIMESTAMP,
  entry_price DOUBLE PRECISION,
  end_date TIMESTAMP,
  source TEXT,
  source_filename TEXT,
  created_at TIMESTAMP DEFAULT now()
);

-- Prevent duplicate open trades with same key (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_trade_key
  ON trades (ticker, direction, entry_date, entry_price)
  WHERE end_date IS NULL;

-- imported_files table (importer also ensures this table exists, but create here for CI init)
CREATE TABLE IF NOT EXISTS imported_files (
  id SERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  file_hash TEXT NOT NULL UNIQUE,
  imported_at TIMESTAMP DEFAULT now()
);
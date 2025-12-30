-- Migration: Create partial unique index for open trades
-- This index is used by the import_blofin_csv.py importer to prevent duplicate open trades
-- and to enable the ON CONFLICT clause for efficient deduplication.

-- Note: CREATE INDEX CONCURRENTLY cannot be run inside a transaction block.
-- Run this migration with autocommit=True or outside a transaction.

-- Create unique partial index on open trades (end_date IS NULL)
-- This prevents duplicate open trades with the same ticker, direction, entry_date, and entry_price
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uniq_open_trade_on_fields
ON trades (ticker, direction, entry_date, entry_price)
WHERE end_date IS NULL;


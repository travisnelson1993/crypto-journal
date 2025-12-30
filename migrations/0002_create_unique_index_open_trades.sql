BEGIN;
-- Create a unique partial index on open trades (where end_date IS NULL)
-- to prevent duplicate open trades and enable ON CONFLICT clause in imports.
-- This index is used by import_blofin_csv.py for efficient duplicate detection.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
ON trades (ticker, direction, entry_date, entry_price)
WHERE end_date IS NULL;
COMMIT;

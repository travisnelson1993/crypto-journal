BEGIN;
-- Interpret existing imported_at values as America/Los_Angeles local time
-- and convert the column to timestamptz (timestamp with time zone).
ALTER TABLE imported_files
  ALTER COLUMN imported_at TYPE timestamptz
  USING imported_at AT TIME ZONE 'America/Los_Angeles';
COMMIT;
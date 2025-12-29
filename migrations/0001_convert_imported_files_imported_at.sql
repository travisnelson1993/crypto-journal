BEGIN;
ALTER TABLE imported_files
  ALTER COLUMN imported_at TYPE timestamptz
  USING imported_at AT TIME ZONE 'America/Los_Angeles';
COMMIT;

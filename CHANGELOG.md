# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Pre-commit configuration with black, isort, and ruff hooks for code quality
- CI workflow with PostgreSQL service, alembic migrations, and test suite
- Migration idempotency: `imported_files` table creation now uses `CREATE TABLE IF NOT EXISTS`

### Changed
- Importer behavior: Close executions now match to the most-recent open trade (LIFO-style matching)
- Migration `20260104_add_imported_files_and_convert_prices`: 
  - Creates `imported_files` table to track imported CSV files and prevent duplicates
  - Converts price columns (`entry_price`, `exit_price`, `stop_loss`) from `numeric` to `double precision`
  - **Note**: Price column type change may affect decimal precision in some edge cases

### Infrastructure
- Added `.gitignore` entries for transient importer logs (`importer_stdout.txt`, `importer_stderr.txt`)
- Migration file now includes note about alembic stamping for manually-applied schemas

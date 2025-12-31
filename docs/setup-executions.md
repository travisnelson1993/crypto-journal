# Executions model & local Postgres for tests

This document explains how to run the new executions model integration tests locally and in CI.

Prereqs:
- Python 3.8+
- pip env with your project's requirements
- Docker (optional for local Postgres)

Local quick run (SQLite in-memory):
1. Install deps:
   pip install -r requirements.txt
   pip install alembic

2. Run tests (fast, SQLite in-memory fallback used by tests):
   pytest -q

Local Postgres run (recommended to test real behavior):
1. Start Postgres:
   docker run --rm --name pg-test -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=test_db -p 5432:5432 -d postgres:15

2. Export DATABASE_URL:
   export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/test_db

3. Run Alembic migrations:
   alembic upgrade head

4. Run tests:
   pytest -q

Notes:
- The importer supports idempotency via `source_rowhash` (a hash of the csv row). If you have a unique source row identifier, ensure it's provided to avoid duplicate inserts.
- Matching uses `SELECT ... FOR UPDATE SKIP LOCKED` when running against Postgres, allowing concurrent import workers. SQLite runs a fallback non-locked matching and is suitable only for local development / simple tests.

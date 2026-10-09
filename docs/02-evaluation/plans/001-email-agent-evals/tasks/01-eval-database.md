# 001/01 — Eval database in Docker

**Goal**: `prepare` builds a fresh, seeded local Postgres for evaluations.

**Why**: Every later step needs an isolated database that never touches the app's Supabase data.

**Scope**
- `docker-compose.eval.yml` with a pgvector Postgres on a non-default port (e.g. 5433).
- `backend/.env.eval` documented (gitignored by `.env.*`); it sets only `DATABASE_URL`.
- A guard used by every eval entrypoint: refuse to run unless the database host is `localhost` or `127.0.0.1`.
- `evals/prepare.py` first half: empty the database, run `alembic upgrade head`, seed two fake users; user A has an active and an inactive mailbox, user B one active mailbox (existing provider value).
- Add `evals` to ruff's `known-first-party`.

**Out of scope**: ingesting emails (001/05); generated data.

**Likely areas affected**: repo root or `backend/` compose file, `backend/evals/`, `backend/pyproject.toml`.

**Acceptance criteria**
- `docker compose -f docker-compose.eval.yml up -d` then `uv run --env-file .env.eval python -m evals.prepare` produces migrated tables and the seeded users and mailboxes.
- Running `prepare` without `--env-file` exits with a clear "not localhost" error before any database call.
- Running `prepare` twice yields the same state.

**Test strategy**
- Unit (`tests/evals/`): the guard accepts localhost URLs and rejects Supabase-style URLs.
- Manual: the commands above; inspect tables with `psql`.

**Dependencies**: none.

**Review notes**: The guard must run before anything creates the cached engine. Emptying the database is destructive; it must be impossible to reach without passing the guard.

**Complexity**: Small.

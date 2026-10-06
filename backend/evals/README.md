# Email agent evaluations

Offline evaluations for the email agent. Plan: [docs/02-evaluation/plans/001-email-agent-evals](../../docs/02-evaluation/plans/001-email-agent-evals/README.md).

Every command runs against a local Docker Postgres, never the app database, and refuses to start unless the database host is local.

## Setup

Create the gitignored `backend/.env.eval` with one line:

```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/folio_eval
```

Values in `.env.eval` override `backend/.env`; everything else (API keys) still comes from `.env`.

## Commands

Run from `backend/`.

```bash
# Start the eval database (pgvector Postgres on localhost:5433)
docker compose -f docker-compose.eval.yml up -d

# Rebuild it: drop everything, migrate, seed fake users and mailboxes
uv run --env-file .env.eval python -m evals.prepare
```

Seeded fixtures (`evals/fixtures.py`): user A with an active and an inactive mailbox, user B with one active mailbox.

## Generating data

```bash
# Plan a scenario with gpt-6.1-sol, then render ~60 .eml files (about 4 minutes, under $1)
uv run python -m evals.generate

# Keep the scenario, re-render only the emails
uv run python -m evals.generate --reuse-scenario
```

Writes to the gitignored `evals/data/draft/`: `scenario.json` (senders, emails with intended label and facts, traps, unanswerable topics) and `emails/*.eml`. Headers come from the scenario; the LLM writes only bodies, and every body is parsed with the production parser and checked to contain its facts (up to three render attempts). Prompts are in `evals/prompts/` and use their own label definitions, not the production classifier's.

## Scoping integration test

Proves against the eval database that email search returns only the user's active-mailbox mail. Needs `prepare` to have run; it rolls back everything it writes and makes no network calls.

```bash
uv run --env-file .env.eval pytest -m integration tests/retrieval/email
```

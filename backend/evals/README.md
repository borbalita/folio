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

# Rebuild it: drop everything, migrate, seed fake users and mailboxes,
# and ingest data v1 with real embeddings and Jev labelling (under a minute, cents)
uv run --env-file .env.eval python -m evals.prepare [--version v1]
```

Seeded fixtures (`evals/fixtures.py`): user A with an active and an inactive mailbox, user B with one active mailbox. The data version's emails go into user A's active mailbox through the normal `ingest_messages`.

`prepare` prints the ingestion summary and every email whose stored label differs from the scenario (borderline-label traps are marked). Mismatches are reported, never corrected. It writes the gitignored `evals/out/ids-<version>.json`, mapping scenario email keys to database email and chunk IDs. Rerun `prepare` only when data or ingestion code changes; runs reuse the database.

## Generating data

```bash
# Plan a scenario with gpt-6.1-sol, render ~60 .eml files, derive cases (about 5 minutes, under $1)
uv run python -m evals.generate

# Keep the scenario; re-render emails and rewrite cases
uv run python -m evals.generate --reuse-scenario
# Keep scenario and emails; only rewrite cases
uv run python -m evals.generate --cases-only# Add N hard-to-label emails per label (borderline-label traps only), render just those,
# and rewrite label cases; RAG cases are unaffected
uv run python -m evals.generate --out evals/data/v1 --add-hard 1
```

Output goes to the gitignored `evals/data/draft/` (`--out` to change):

- `scenario.json`: senders, emails with intended label and facts, traps (near-duplicate, date boundary, borderline label), unanswerable topics.
- `emails/*.eml`: headers come from the scenario; the LLM writes only bodies, and every body is parsed with the production parser and must contain its facts verbatim (up to three render attempts).
- `rag_cases.jsonl`: question, fixed `today`, retrieval probe (query and filters), expected emails and facts, answerable flag, distractors, split. Everything except the question wording is derived in code from the scenario; the LLM phrasing questions never sees fact values, and questions that contain an answer or copy a subject are rejected.
- `label_cases.jsonl`: email key, expected label, split (about 60/40 per label).

Prompts are in `evals/prompts/`; `labels.md` holds the generator's own label definitions, separate from the production classifier's.

### Data versions

The committed benchmark lives in `evals/data/v1/` (promoted with `mv evals/data/draft evals/data/v1`): 60 generated emails plus 5 hard labelling emails (`e61`–`e65`) from `--add-hard 1`. v1 may still be regenerated until its first Langfuse sync; after that it is frozen and changes go into `v2`.

## Running evaluations

Needs `prepare` to have run for the same data version.

```bash
# Retrieval test: real email search with each case's fixed query and filters, no chat model
# (about 1.5 minutes; embedding and keyword-helper calls only)
uv run --env-file .env.eval python -m evals.run --mode retrieval [--version v1]
```

Each run prints per-case scores and averages (overall and per case kind) and writes a JSON report to the gitignored `evals/out/reports/`.

Retrieval metrics are per email, not per chunk; each email takes the rank of its first chunk, with k = `retrieval_top_k` (10):

- **recall@10**: expected emails found in the top 10 / expected emails.
- **precision@10**: expected emails / emails returned. Search almost always fills all 10 slots, so with one expected email this sits near 0.1; read MRR for ranking quality.
- **MRR**: 1 / rank of the first expected email, 0 if none.

Unanswerable cases have no expected email; they are reported as not applicable and counted separately. The report also lists which distractors (near-duplicate twins, near misses) were retrieved.

## Scoping integration test

Proves against the eval database that email search returns only the user's active-mailbox mail. Needs `prepare` to have run (with or without ingested data); it rolls back everything it writes and makes no network calls.

```bash
uv run --env-file .env.eval pytest -m integration tests/retrieval/email
```

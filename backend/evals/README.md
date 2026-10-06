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

## Langfuse

Eval commands need `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (from `backend/.env`) and stop without them.

```bash
# Upload the case files to the datasets email-rag-v1 and email-labels-v1
uv run python -m evals.langfuse_sync [--version v1]
```

Rerunning `sync` is safe: unchanged items are skipped. An item whose content differs from the committed case is refused, because a version is frozen once synced; put changes into a new version (`v2`). Runs refuse to start if the dataset does not match the committed cases.

Each run is one Langfuse experiment (dataset run) for one mode and one model or variant, with a score per item and metadata: Git commit (`-dirty` if uncommitted), mode, subject (model or variant), data version, fixed today, and hashes of the prompts involved. Eval traces land in the `sdk-experiment` environment with the tags `eval`, `mode:<mode>`, and `data:<version>`, and the app's spans (search, agent, tools) nest under each item. Scores are computed locally; if publishing fails, the local report is still written, marked `"published": false`, and the command exits non-zero. Nothing is re-run to retry an upload.

## Running evaluations

Needs `prepare` and `sync` to have run for the same data version.

```bash
# Retrieval test: real email search with each case's fixed query and filters, no chat model
# (about 1.5 minutes at concurrency 1, 35 seconds at 4; embedding and keyword-helper calls only)
uv run --env-file .env.eval python -m evals.run --mode retrieval [--version v1] [--concurrency 4]
```

Concurrency defaults to 1 (stops early on bugs, readable traces); raise it to 4–5 once a mode is stable. Each run prints per-case scores, averages (overall and per case kind), and the Langfuse run URL, and writes a JSON report to the gitignored `evals/out/reports/`.

Retrieval metrics are per email, not per chunk; each email takes the rank of its first chunk, with k = `retrieval_top_k` (10):

- **recall@10**: expected emails found in the top 10 / expected emails.
- **precision@10**: expected emails / emails returned. Search almost always fills all 10 slots, so with one expected email this sits near 0.1; read MRR for ranking quality.
- **MRR**: 1 / rank of the first expected email, 0 if none.

Unanswerable cases have no expected email; they are reported as not applicable (no score in Langfuse) and counted separately. The report also lists which distractors (near-duplicate twins, near misses) were retrieved.

## Scoping integration test

Proves against the eval database that email search returns only the user's active-mailbox mail. Needs `prepare` to have run (with or without ingested data); it rolls back everything it writes and makes no network calls.

```bash
uv run --env-file .env.eval pytest -m integration tests/retrieval/email
```

## News extraction benchmark

Compares models for AI-newsletter item extraction (`ingest/email/news.py`) on the owner's real newsletters. Plan: [docs/02-evaluation/plans/003-news-extraction](../../docs/02-evaluation/plans/003-news-extraction/README.md).

Unlike the rest of this folder, it uses real data, and its export is the one eval command that reads the app database (read only). The newsletters contain per-recipient tracking links, so they never go into git: the working copy is gitignored, and the lasting copy is the Langfuse dataset `news-extraction-v1` (backup in a private Supabase Storage bucket).

```bash
# Export the stored ai_newsletter emails (app database, read only) to evals/data/news-v1/
uv run python -m evals.news_export

# Run one model over every newsletter; outputs, tokens, cost, and latency go to evals/out/news-runs/
uv run python -m evals.news_runs --model gpt-5.4-nano --effort none

# Answer key from the GPT-5.5 reference run (what news-v1 uses)
uv run python -m evals.news_review reference

# Or hand-label: review page on 127.0.0.1:8765, then build the answer key from the decisions
uv run python -m evals.news_review serve
uv run python -m evals.news_review build

# Freeze: upload to the Langfuse dataset news-extraction-v1, back up to the private
# eval-datasets bucket, then delete the local newsletters (--keep-local to keep them)
uv run python -m evals.news_sync
```

A URL counts only when it is an http(s) article link that appears verbatim in the newsletter text; front-page footer links and button labels don't. The answer key stores no link otherwise, and a run's link that isn't in the text counts as invented.

### Ground truth: GPT-5.5, not hand labels

news-v1's answer key is the GPT-5.5 default-effort output, not human-checked answers, so scores measure agreement with GPT-5.5 rather than correctness: GPT-5.5's own mistakes count as right, and a cheaper model that fixes one is marked down. That is enough to answer "can a cheaper model replace today's extraction without changing what gets stored".

In a real project we would hand-label at least part of the data before switching models on these numbers: a few fully checked newsletters per source, to catch mistakes every model shares, plus the items where models disagree, which is where a cheaper model's errors show up. `news_review serve` and `build` are built for exactly that.

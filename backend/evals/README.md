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
uv run python -m evals.generate --cases-only
# Add N hard-to-label emails per label (borderline-label traps only), render just those,
# and rewrite label cases; RAG cases are unaffected
uv run python -m evals.generate --out evals/data/v1 --add-hard 1
# Copy a committed version, add story lines, look-alike filler, and planned questions
# (multi_email, superseded, vague, unanswerable); existing cases keep their wording
uv run python -m evals.generate --extend-from v1 --out evals/data/v2
```

Output goes to the gitignored `evals/data/draft/` (`--out` to change):

- `scenario.json`: senders, emails with intended label and facts, traps (near-duplicate, date boundary, borderline label), unanswerable topics.
- `emails/*.eml`: headers come from the scenario; the LLM writes only bodies, and every body is parsed with the production parser and must contain its facts verbatim (up to three render attempts).
- `rag_cases.jsonl`: question, fixed `today`, retrieval probe (query and filters), expected emails and facts, answerable flag, distractors, split. Everything except the question wording is derived in code from the scenario; the LLM phrasing questions never sees fact values, and questions that contain an answer or copy a subject are rejected.
- `label_cases.jsonl`: email key, expected label, split (about 60/40 per label).

Prompts are in `evals/prompts/`; `labels.md` holds the generator's own label definitions, separate from the production classifier's.

### Data versions

The committed benchmark lives in `evals/data/v1/` (promoted with `mv evals/data/draft evals/data/v1`): 60 generated emails plus 5 hard labelling emails (`e61`–`e65`) from `--add-hard 1`. v1 is synced and frozen.

`evals/data/v2/` extends v1 (plan 002): the same 65 emails and 31 cases, plus 50 emails (`e66`–`e115`) in linked story lines and look-alike filler, and 18 planned cases (`c32`–`c49`). Its stories prompt is `prompts/stories.md`. New emails never repeat a v1 fact under the same fact name, so v1 cases keep a single answer; `--cases-only` keeps existing wording and v1 label splits.

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
uv run --env-file .env.eval python -m evals.run --mode retrieval --rerank off [--version v2] [--concurrency 4]
# Same with Jev evidence reranking: 20 fused candidates judged per search, then reordered and cut
uv run --env-file .env.eval python -m evals.run --mode retrieval --rerank on --version v2 --concurrency 4
```

`--rerank` is required so every run, report, and Langfuse subject says which search it measured. Search results vary slightly between runs (the keyword helper is an LLM), so compare several runs of each. The summary also gives seconds per search (mean, p95, max), which includes reranking.

Concurrency defaults to 1 (stops early on bugs, readable traces); raise it to 4–5 once a mode is stable. Each run prints per-case scores, averages (overall and per case kind), and the Langfuse run URL, and writes a JSON report to the gitignored `evals/out/reports/`.

Retrieval metrics are per email, not per chunk; each email takes the rank of its first chunk, with k = `retrieval_top_k` (10):

- **recall@10**: expected emails found in the top 10 / expected emails.
- **recall@3**: the same within the top 3; with only ~100 emails, recall@10 is nearly always 1.0.
- **precision@10**: expected emails / emails returned. Search almost always fills all 10 slots, so with one expected email this sits near 0.1; read MRR for ranking quality.
- **MRR**: 1 / rank of the first expected email, 0 if none.
- **distractor rate**: the case's planned distractors (outdated values, near-duplicate twins, look-alikes, near misses) returned in the top 10 / planned distractors. Lower is better: the agent can't quote an outdated value it never sees.
- **empty**: unanswerable cases only; 1.0 when search returns nothing.

Unanswerable cases have no recall, precision, or MRR; Langfuse gets no score for a metric that doesn't apply. The report also lists which distractors were retrieved.

### Answer test

The real email agent answers each case, but search is replaced by `ReplayRetriever`: every `search_emails` call returns the case's expected and distractor emails (in an order fixed per case), or nothing for an unanswerable case without distractors. Search quality doesn't affect the result, so this measures answering only.

```bash
# One run per model; candidates go through the Responses API at their default effort
uv run --env-file .env.eval python -m evals.run --mode answer --model gpt-6-luna --version v2 [--effort none] [--concurrency 2]
```

Scores, each only where it applies:

- **refusal_correct**: `insufficient_evidence` matches whether the case is answerable; the comment says `wrong_refusal` or `missing_refusal`.
- **evidence_cited**: answerable cases; the answer cites at least one chunk of an expected email.
- **distractor_cited**: when distractors were in the evidence and the model answered. Diagnostic: citing the older email next to the current one is often right.
- **grounding_pass**: `EmailGrounder`'s citation checks on the model's own answer; not scored for unanswerable cases with no evidence.

The report keeps each case's answer, cited emails, tool calls with their results, token usage, and seconds. Whether stated facts are right needs the judge (001/11).

### End-to-end run

The normal agent path: the model chooses its own searches and filters over the real email index, so search decisions and answering are tested together. Reranking is explicit, as in the retrieval test.

```bash
uv run --env-file .env.eval python -m evals.run --mode e2e --model gpt-6-luna --rerank off --version v2 [--effort none] [--concurrency 4]
```

Scores are the answer test's, with two differences: `distractor_cited` counts only distractors the agent's searches actually returned, and `grounding_pass` applies whenever the agent saw any email. Added:

- **search_recall**: answerable cases; the share of expected emails returned by at least one of the agent's searches. It pools every call, so it isn't recall@10.

Each search is kept with its query, filters (`since`, `until`, `label`, `sender`, `mailbox`), and the emails returned, so a failure from a wrong filter is visible; the `search_recall` comment in Langfuse lists them. The summary adds searches per case and cases with no search.

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

# Score a model against the frozen dataset as a Langfuse experiment (no database involved)
uv run python -m evals.run --mode extraction --model gpt-5.4-nano --effort none --concurrency 4
# Score a saved local run instead of calling the model again (used for GPT-5.5)
uv run python -m evals.run --mode extraction --model gpt-5.5 --replay
```

Metrics per newsletter and pooled over all of them: recall and precision of news items, `url_exact` (found items whose URL equals the expected one), `order`, `sponsor_leaks` (sponsors returned as news), `sponsor_drops` (news flagged as sponsors), `invented_urls`, cost, and latency. The pass bar from the plan is recall ≥ 0.97, url_exact ≥ 0.98, and no sponsor leaks or invented URLs. Replaying GPT-5.5 against its own answer key scores 1.0 except url_exact 0.993 and 2 invented URLs: two GitHub links it guessed for an Alpha Signal edition that contains no links. The url_exact gap is 3 TLDR items (n24, n39, n42) whose real links an earlier version of the link rule dropped from the frozen answer key; they cost every model the same at most 0.4%.

A URL counts only when it is an http(s) link that appears verbatim in the newsletter text and isn't the newsletter's own front page (the footer link in every edition); button labels copied into the URL field don't count either. A third-party front page can be an item's real link. The answer key stores no link otherwise, and a run's link that isn't in the text counts as invented.

### Ground truth: a model's output, not hand labels

| Dataset | Answer key | Build it with |
|---|---|---|
| `news-extraction-v1` | GPT-5.5, default effort | `news_review reference` |
| `news-extraction-v2` | GPT-6 Astra, effort low | `news_review reference --run gpt-6-astra@low` |

Score against v2 with `--version news-v2`. An official run's report keeps every extracted item, so `uv run python -m evals.news_runs --from-report <report> --version news-v2` saves it as a run for replays or for a later answer key, without calling the model again.

The note below was written for v1 and applies to v2 the same way.

Each version's answer key is one model's output, not human-checked answers, so scores measure agreement with that model rather than correctness: its mistakes count as right, and a model that fixes one is marked down. That is enough to answer "can a cheaper model replace today's extraction without changing what gets stored".

In a real project we would hand-label at least part of the data before switching models on these numbers: a few fully checked newsletters per source, to catch mistakes every model shares, plus the items where models disagree, which is where a cheaper model's errors show up. `news_review serve` and `build` are built for exactly that.

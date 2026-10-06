# 001 — Email agent evaluations

- Created: 2026-10-02
- Status: In progress
- Current stage: Implementation; starting with 001/01 and 001/08.

## Approval state

Approved on 2026-10-02: focus on the email agent, narrowed to labelling and email RAG; goals, failures, and constraints below; all decisions; the design. Approved on 2026-10-06: the validated task plan, `gpt-6.1-sol` as generation model, and the implementation checkpoints below. Discovery writes documentation only.

## Problem

The email agent answers questions about the user's mail and AI newsletters, but nothing measures whether its answers are right. Without that, the product can't be trusted, and changes to prompts, retrieval, or models can't be judged as improvements or regressions.

This is a portfolio project whose main purpose is learning how to do evaluations properly, so the approach should follow sound evaluation practice rather than the quickest check.

## Current system

- [Email agent](../../../../backend/app/email_assistant/agent.py): a PydanticAI agent with three tools: `search_emails` (hybrid search over mail with mailbox, sender, label, and date filters), `search_news` (semantic search over newsletter items), and `list_big_news` (stories covered by both TLDR and Alpha Signal). The prompt injects today's date; [instructions](../../../../backend/app/email_assistant/instructions.md) require a citation for every claim, or an explicit insufficient-evidence answer.
- [Ingestion](../../../../backend/ingest/email/): parses messages, labels them (registered newsletter senders become `ai_newsletter` by rule; everything else goes to a TypeSafe-backed classifier), extracts news items, and groups them into stories. Answers depend on this upstream work being correct.
- [Grounding](../../../../backend/app/grounding.py): checks citation structure (cited IDs were retrieved, indexes unique, no citations on insufficient-evidence answers). It does not check that the cited text supports the answer.
- [Tracing](../../../../backend/app/observability.py): agent runs, tool calls, and retrieval steps are exported to Langfuse with user and session attributes. No scores are recorded.
- [Legacy evals proposal](../../legacy/evals-todo.md): written for the document copilot and partly outdated. Useful leftovers: grounding outcomes as Langfuse scores, and an offline evaluation run.

## Goals

Scope: email labelling and RAG over email (`search_emails`). Newsletter tools are later work.

- Measure email agent answer quality against explicit expectations, and see why individual cases fail.
- Tell whether a change (prompt, retrieval, model) improved or regressed quality.
- Benchmark how answer quality varies with the agent's chat model.
- Benchmark labelling prompt variants (and optionally models) against each other.
- Learn sound evaluation practice along the way.

### Failures that matter

Each must be detectable by the evaluation:

- **Wrong fact**: a stated date, amount, sender, or other detail is wrong.
- **Missed evidence**: an email that answers the question isn't found or used.
- **Unsupported citation**: cited mail doesn't actually support the claim.
- **Wrong refusal**: says the mailbox has no answer when it does.
- **Missing refusal**: answers confidently when the mailbox has no answer.
- **Mislabelled email**: ingestion assigns the wrong label, which can hide mail from label-filtered searches.

Wrong filters (date range, sender, mailbox) were not singled out; they are a common cause of missed evidence and wrong refusals and are diagnosed under those.

## Non-goals

- The document copilot.
- Everything under [Later](#later).

## Decisions

### Synthetic data is generated scenario-first

One command generates everything: an LLM writes a structured scenario (senders, invoices, replies, ordinary newsletters and promotions, planted traps such as near-duplicates, date boundaries, borderline labels, and unanswerable questions). No AI newsletters (TLDR, Alpha Signal) are generated while newsletter tools are out of scope; an LLM renders it into realistic `.eml` files; code derives questions and expected results from the scenario. Expected answers are correct by construction, so no manual review is needed. Rejected: emails-first generation with an LLM or Ragas writing questions afterwards, since its expected answers need review and it rarely produces deliberate traps; Ragas also adds a large dependency. Approved 2026-10-02.

### The synthetic mailbox lives in a local Docker Postgres

Synthetic mail is ingested into a local Postgres + pgvector container, not the app database, so fake mail never appears in the real app and the eval mailbox can be wiped and rebuilt freely. This also matters once newsletter tools are evaluated: `rebuild_stories` groups news items across the whole database and would merge fake stories with real ones. Ingestion and retrieval use `database_url` through SQLAlchemy and migrations are not Supabase-specific, so no code changes are needed. Docker is dev tooling only. Rejected: a second Supabase project (more to manage, slower to reset). Approved 2026-10-02.

### Three test modes

- **Retrieval test**: run the real `search_emails` retrieval with each case's fixed query and filters (from the scenario) and compare results with the expected emails. Reports recall and precision; the design adds a rank- or cutoff-based measure because precision at a fixed top *k* is capped when few results are relevant. No chat model involved.
- **Answer test with fixed evidence**: the chat model receives the question and preset tool results (expected evidence, sometimes with distractors, or empty), via replay versions of the agent's tools. Grades facts, citations, and refusals.
- **End-to-end run**: the normal agent path; the model chooses tools and filters itself. Shows whether the steps work together and tests the model's search decisions.

The model benchmark compares chat models on the answer test and the end-to-end run. Email search uses the configured chat model only for its keyword helper, which stays fixed during the benchmark, so search behaves identically across models. Approved 2026-10-02.

### Benchmark OpenAI chat models; judge with Claude

Compare OpenAI chat models only (see Models, sizes, and cost). The judge is an Anthropic model, so it shares fewer blind spots and less style preference with the candidates. This is an eval-only exception to the OpenAI stack: the `anthropic` SDK is already locked through `pydantic-ai`, so it adds an API key and an optional setting, not a package. Approved 2026-10-02.

### Cases in Git, judge in code

The generated scenario, emails, and cases are committed, freezing one version so runs stay comparable and the set is visible in the portfolio; a sync step uploads cases to a version-named Langfuse dataset for experiments. The judge is a Python function with its rubric prompt in Git, run inside the experiment alongside the code checks. Rejected: Langfuse-only cases (not reviewable, regeneration breaks comparisons) and a Langfuse-managed judge (rubric outside Git, runs separately). Approved 2026-10-02.

### Labelling test with variants

A separate labelling test calls `label_message` through its existing `classifier` parameter and compares predicted with scenario labels: per-label precision, recall, F1, and a confusion table. Each run compares *variants* (model plus label descriptions and input format), starting with Jev and prompt variants; other models are just more variants. Variants live in the eval package; a winning variant is copied into `labels.py` in a normal change. Emails are split into tuning and held-out sets, and the generator uses its own label definitions and includes borderline emails so the test isn't circular. `ai_newsletter` is assigned by sender rule and is outside the benchmark. A label check after ingestion also confirms the eval mailbox matches the scenario. Rejected: only checking labels after ingestion, which can't compare variants. Approved 2026-10-02.

### Scoping is a normal test, not an eval

"Search never returns mail from another user or an inactive mailbox" is a security property with a single correct answer, so it belongs in pytest. Existing unit tests check the scope SQL text and mocked filtering; this plan adds an integration test (`@pytest.mark.integration`) that runs the real email search against the Docker Postgres seeded with a second user and an inactive mailbox. Approved 2026-10-02.

## Design

### Components and flow

```text
generate ──► evals/data/v1/  (committed: scenario.json, emails/*.eml, rag_cases.jsonl, label_cases.jsonl)
                 │
prepare  ──► Docker Postgres: migrate, seed fake users and mailboxes, ingest .eml files
                 │           with normal ingestion, check stored labels against the scenario
run      ──► one mode per run: retrieval | answer | e2e | labelling
                 ├──► local report (gitignored)
                 └──► Langfuse experiment (dataset synced from the case files)
```

```text
backend/evals/
  generate.py      # scenario → emails + cases, one command
  prepare.py       # build the eval mailbox in Docker
  run.py           # entrypoint: --mode retrieval|answer|e2e|labelling
  modes/           # one small module per mode
  scoring.py       # code checks
  judge.py         # LLM judge; rubric in rubric.md
  data/v1/         # committed generated data
  README.md        # commands
docker-compose.eval.yml   # pgvector Postgres
```

The package sits beside `app/` and is not collected by the normal pytest suite.

**Prepare** always rebuilds from scratch: empty the database, run migrations, seed two fake users (one with an active and an inactive mailbox, used by the scoping integration test), and ingest the emails through `ingest_messages`. It reruns only when data or ingestion code changes; runs reuse the database. Ingestion makes real embedding and Jev calls (cents for ~50 emails).

**Database targeting.** Eval commands run as `uv run --env-file .env.eval ...`, where the gitignored `backend/.env.eval` sets `DATABASE_URL` to the local container. Environment variables take priority over `backend/.env`, so the whole process, including the cached engine and Alembic, uses Docker with no app code changes. Every eval command first refuses to run unless the database host is `localhost`. Rejected: an `EVAL_DATABASE_URL` setting, which would require swapping the URL at runtime before the cached engine is built (fragile) or eval logic in `engine.py`.

### RAG test modes

**Retrieval test.** Calls `EmailRetriever().search(query, filters=...)` with each case's query and filters as the fake user. Chunks are grouped by email, keeping each email's first rank; `prepare` writes a local map from scenario email keys to database IDs. Metrics at email level with *k* = `retrieval_top_k` (10): recall@10, precision@10, and MRR (1 / rank of the first expected email). Unanswerable cases are excluded from recall and counted separately.

**Answer test.** Runs the real agent with `deps.retriever` replaced by a `ReplayRetriever` that ignores the query and returns the case's preset chunks from the Docker database: expected emails, optionally a distractor, or nothing. Citation IDs are real, so grounding works unchanged, and no production code changes.

**End-to-end run.** The same as the answer test with the real `EmailRetriever`.

Shared by both agent modes:

- **Fixed today**: an optional `today` parameter on `email_prompt` (the only production change); normal use is unchanged.
- **Step record**: the eval calls the cached agent directly and keeps the full PydanticAI message history (tool calls, arguments, results, final answer).
- **Grounding**: `EmailGrounder` runs after each answer and is recorded as a pass/fail score; the model's own answer is graded, not the canned rejection reply.
- **Model per run**: `agent.run(..., model=...)` selects the chat model (verify against PydanticAI 2.46). The keyword helper stays on the configured model.

### Labelling test

A variant is a set of label descriptions plus an input builder; the baseline copies today's descriptions and reuses the production input builder (sender, subject, attachment names, first 4,000 body characters). Variants live in `evals/labelling/variants.py` and call Jev through the same TypeSafe provider as production.

Each variant gets one call per email, with no retry or fallback: an invalid answer counts as wrong and is reported as "invalid", so a fallback to `other` can't hide broken variants. Production's retry and fallback are exercised by `prepare`'s stored-label check.

Reported per variant: accuracy, per-label precision, recall, F1 with support counts, macro-F1, a confusion table, and the invalid count. Cases are split about 60/40 into `tuning` and `held_out`, balanced by label; only held-out numbers decide between variants.

### Scoring and judge

Scores for the answer test and end-to-end run:

| Failure | Score | Check |
|---|---|---|
| Wrong / missing refusal | `refusal_correct` | Code: `insufficient_evidence` vs the case's answerable flag; outcome labelled `wrong_refusal` or `missing_refusal` |
| Missed evidence | `evidence_cited` | Code: the answer cites at least one expected email; end-to-end also reports retrieval recall from recorded tool results |
| Unsupported citation | `faithfulness` | Judge: supported claims / claims, against the full text of cited chunks |
| Wrong fact | `fact_recall` | Judge: expected scenario facts stated correctly / expected facts |
| Structure | `grounding_pass` | Code: `EmailGrounder` |

Facts use the judge because the agent formats dates and amounts in many ways; the expected facts still come from the scenario. The judge makes two calls per answer with separate rubric files: *support* (claims, each with reason and `supported`/`not_supported`; simple correct inferences count as supported) and *facts* (each expected fact with reason and `correct`/`wrong`/`missing`). Email text and answers are passed as marked data, never instructions. With nothing to judge (e.g. a refusal), the score is not applicable, never 1.0.

**Calibration**: after the first run, ~30 outputs go to a Langfuse annotation queue for hand grading; a script reports agreement and the judge-passed-human-failed rate. Judge scores are trusted only after that.

### Langfuse reporting

`sync` uploads `rag_cases.jsonl` and `label_cases.jsonl` to version-named datasets (`email-rag-v1`, `email-labels-v1`); rerunning is safe. Each run is one `run_experiment` for one mode and one model or variant, with per-case scores. Run metadata: Git commit, mode, model or variant, data version, fixed today, prompt and rubric hash. Concurrency is a run option, default 1 (stop early on bugs, stay under rate limits, readable traces), raised to about 4–5 once a mode is stable. Every run also writes a local JSON report, since free-tier data expires.

### Models, sizes, and cost

- **Candidates**: `gpt-6-luna` and `gpt-6.1-sol`. The app's current `gpt-5.5` and `gpt-6-astra` are left out for now; each is a one-line addition.
- **Judge**: Claude Sonnet 5.5, with an optional `anthropic_api_key` setting used only by evals.
- **Sizes**: about 60 emails (about 12 per model-assigned label) and about 30 RAG cases, roughly 8 unanswerable, shared by all RAG modes.
- **Runs**: a normal run is one pass per model and mode; a final benchmark repeats each three times.

Estimated cost (2026-10-02 list prices, about 6k input and 1.5k output tokens per agent case; check against the first real run):

| Item | Normal run | Final benchmark |
|---|---|---|
| Luna, 2 agent modes | ~$0.10 | ~$0.25 |
| Sol, 2 agent modes | ~$1.60 | ~$5 |
| Sonnet judge | ~$2 | ~$6.50 |
| Generation and embeddings | under $1, once per data version | — |

Jev labelling is about 100 times cheaper than regular chat models, so labelling runs are negligible.

### Generation

`generate` writes the scenario as structured data, renders each email with an LLM, then checks in code that every rendered email contains its key scenario facts (amounts, dates, sender, subject). Emails failing the check are re-rendered, so expected answers stay correct by construction. Questions and expected results are derived from the scenario in code; questions are phrased with an LLM so they don't copy email wording.

## Success criteria

- From `evals/README.md` alone: `generate`, `prepare`, and `run` for each mode work with one command each.
- `prepare` builds the Docker mailbox and reports any stored-label mismatches against the scenario.
- Every mode writes a local report and a Langfuse experiment with per-case scores; Luna and Sol can be compared case by case in Langfuse.
- The judge is calibrated on about 30 hand-graded outputs, with agreement reported per candidate model.
- The labelling test compares the baseline with at least one prompt variant on the held-out set.
- The scoping integration test passes under `pytest -m integration`.
- A normal run stays within a few euros.
- `uv run pytest -m "not integration"` passes, and production behaviour is unchanged apart from the optional `today` parameter.

## Tasks

- [ ] [001/01 — Eval database in Docker](tasks/01-eval-database.md)
- [ ] [001/02 — Scoping integration test](tasks/02-scoping-integration-test.md)
- [ ] [001/03 — Scenario and emails](tasks/03-scenario-and-emails.md)
- [ ] [001/04 — Cases and data v1](tasks/04-cases.md)
- [ ] [001/05 — Ingest data into Docker](tasks/05-ingest-into-docker.md)
- [ ] [001/06 — Retrieval test](tasks/06-retrieval-test.md)
- [ ] [001/07 — Langfuse datasets and experiments](tasks/07-langfuse-experiments.md)
- [ ] [001/08 — Optional reference date in the email prompt](tasks/08-prompt-reference-date.md)
- [ ] [001/09 — Answer test with fixed evidence](tasks/09-answer-test.md)
- [ ] [001/10 — End-to-end run](tasks/10-end-to-end-run.md)
- [ ] [001/11 — LLM judge](tasks/11-judge.md)
- [ ] [001/12 — Judge calibration](tasks/12-judge-calibration.md)
- [ ] [001/13 — Labelling test](tasks/13-labelling-test.md)
- [ ] [001/14 — First benchmark](tasks/14-first-benchmark.md)
- [ ] [001/15 — Documentation](tasks/15-docs.md)

```text
01 ──► 02
01 ──┐
03 ──► 04 ──► 05 ──► 06 ──► 07 ──┬──► 09 ──► 10
             │          08 ──────┘     └──► 11 ──► 12
             └─────────────────────► 13 (needs 04 and 07)
10, 12, 13 ──► 14 ──► 15
```

01, 03, and 08 can start in parallel.

### Validation (Stage 6)

- **Completeness**: every failure in scope maps to a score; every success criterion maps to a task. Fixed gaps: the scoping test also stubs the query embedding (001/02); eval entrypoints initialize and flush tracing (001/07); calibration adds corrupted answers if real failures are scarce (001/12); the generation model is set (001/03).
- **Size**: 001/09 is the largest task; it stays one task because replay, step record, and scores are only testable together.
- **Mergeability**: every task leaves production unchanged except 001/08, which is backwards compatible. Commands are documented by each task as it lands, not only in 001/15.
- **Risk**: highest uncertainty in 001/03 (generation quality) and 001/07 and 001/09 (unverified Langfuse and PydanticAI APIs, checked at the start of each).
- **Scope**: no task goes beyond the agreed scope.

### Implementation checkpoints

Work proceeds task by task, one commit each, without Cursor co-author trailers. Stops for the user:

1. Before 001/03: OpenAI, TypeSafe, and Langfuse keys available to the eval commands.
2. After 001/05: skim the generated emails and the stored-label report.
3. After 001/07: confirm the first Langfuse experiment looks right.
4. Before 001/11: Anthropic key.
5. Before 001/12: hand-grading session.
6. Before 001/14: go-ahead for the paid benchmark (about $12).

Small paid test runs in 001/03 to 001/11 (a few dollars in total) proceed without separate approval once the plan is approved.

## Risks

- **Too-easy data**: if both models score near 100%, the benchmark can't separate them. Check the score spread after the first run and add harder traps if needed.
- **Rendering drift**: an LLM-rendered email may misstate a fact; the generation check catches facts it knows about, not new ones the LLM invents.
- **Small samples**: about 30 cases and about 5 held-out emails per label only reveal large differences.
- **Unverified APIs**: per-run model override and message history in PydanticAI 2.46, and `run_experiment` in Langfuse 4.14.5, need checking before relying on them.
- **Calibration effort**: poor judge agreement means rubric iterations before judge scores are usable.

## Constraints

- Fully synthetic, automatically generated mail and cases are acceptable; this is a portfolio project, so test-set quality is secondary to a sound evaluation workflow. No real usage traces exist yet.
- Budget: a few euros per evaluation run, tens of euros per month.

## Later

Worth evaluating after this plan, roughly in order of value:

- **Prompt injection (highest priority)**: emails containing instructions aimed at the agent. Belongs to a separate, soon-to-follow plan that builds a guardrail; that plan adds injection cases to this plan's synthetic mailbox and uses the same harness to measure the guardrail.
- **Newsletter tools**: `search_news` retrieval over news items, and `list_big_news` checked against the rule "covered by both TLDR and Alpha Signal" (missed or wrongly included stories).
- **News extraction and story grouping**: are all items in a newsletter extracted correctly, and are duplicate reports of one story grouped together?
- **Tool choice and filters as scores**: did the agent pick the right tool and the right date range, sender, or mailbox? (This plan diagnoses them only through failing cases.)
- **PDF attachments**: answers that depend on invoice PDFs.
- **Real mail**: a small, locally kept suite from your own mailbox, reported separately from the synthetic suite.
- **Production scoring**: grounding pass rate, refusal rate, and citation counts recorded as Langfuse scores on live traces, with a dashboard (from the legacy proposal).
- **Multi-turn conversations**, once conversation memory is in place.
- **More models**: other providers for the chat model, and OpenAI models as labelling variants.
- **Regression gate**: run a small eval set before merging changes to prompts or retrieval, once scores are stable.

## Open questions

None blocking the design.

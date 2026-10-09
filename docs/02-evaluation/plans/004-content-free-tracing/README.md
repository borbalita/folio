# 004 — Content-free tracing

- Created: 2026-10-09
- Status: In progress
- Current stage: 004/01 implemented; its live Langfuse check is pending

## Approval state

- 2026-10-08: scope, content definition, local mode, production guard and eval handling settled in chat, one question at a time.
- 2026-10-09: the news datasets stay in Langfuse as a recorded exception (changed from "real data never in Langfuse" at the owner's request). Design sections 1–3 approved; section 4 (evals, tasks) presented and taken as approved when the owner asked for the spec. The eval work merged to main first ([#20](https://github.com/borbalita/folio/pull/20)), so task 04 needs no other branch. Spec approved by the owner.

## Problem

Every agent sends full content to Langfuse: questions, instructions, answers, tool arguments and results, retrieved email and filing text, search queries and filters. The only protection is an email-address regex. The finance plan ([001](../../../05-finance/plans/001-finance-agent/README.md), Design → Privacy) requires that no content reaches Langfuse before invoices (001/05) and the Finance chat (001/12) are built: traces keep models, tools, tokens, timings and errors only, and full content goes to a local trace output behind a local-only setting the API refuses in production. Pattern masking and a Langfuse debug switch were rejected there.

## Current system

- **Setup:** [observability.py](../../../../backend/app/observability.py) registers a global OTel provider, constructs `Langfuse` with an email-regex `mask_otel_spans`, and calls `Agent.instrument_all()` with default settings, so PydanticAI records prompts, instructions, completions, tool arguments and tool results. It runs when Langfuse keys are set; otherwise tracing is off.
- **Hand-made spans with content:**
  - `generate-chat-response` ([orchestrator.py](../../../../backend/app/chat/orchestrator.py)): input is the user text, output the answer or canned reply.
  - `hybrid-search` ([base.py](../../../../backend/app/retrieval/base.py)) and `news-search` ([news/retriever.py](../../../../backend/app/retrieval/news/retriever.py)): input is the query and filters.
  - `embed-query` in both: input is the query.
  - `rerank` ([rerank.py](../../../../backend/app/retrieval/email/rerank.py)): input is the query and question.
- **Not traced:** email ingest ([run.py](../../../../backend/ingest/email/run.py)) never calls `configure_tracing`, so labelling and news extraction are invisible, and so would 001/05's invoice extraction be. Raw OpenAI SDK calls (embeddings, FTS keywords) are not instrumented anywhere.
- **Evals:** [evals/tracing.py](../../../../backend/evals/tracing.py) calls `configure_tracing()`, so app spans nest under each Langfuse experiment item. `eval_tracing()` requires Langfuse keys. The harness itself records item inputs, task outputs and score comments (judge reasons, search queries and filters), from synthetic data except plan 003's real newsletters, whose only lasting copy is the Langfuse datasets `news-extraction-v1/v2`.
- **Railway (2026-10-09):** `backend` has `ENVIRONMENT=production` and Langfuse keys; `email-ingest` has neither (`ENVIRONMENT` defaults to `local`). Railway sets `RAILWAY_ENVIRONMENT_NAME=production` on both.
- **Libraries:** `pydantic-ai-slim` 2.46 (`InstrumentationSettings(include_content=..., include_binary_content=...)`), `langfuse` 4.14.5 (`span_exporter=`; `mask_otel_spans` patches attributes only, not events or status), `opentelemetry-sdk` 1.44.

## Goals and non-goals

Goals:

- No app trace in Langfuse carries content, for every agent and every traced LLM call.
- Errors stay visible by type and status code, without their messages.
- Full content can be seen locally when a setting is on, and that setting cannot run on Railway.
- Email ingest is traced, content-free, before invoice extraction lands in it.
- Evals keep working, and say what changed.

Non-goals: tracing raw OpenAI SDK calls; HTTP or database spans; changing eval scores or datasets; moving the plan 003 datasets out of Langfuse; trace retention or deletion of old Langfuse traces.

## Decisions

- **All agents, not only Finance.** One global rule; email content is at least as private as finance data. Rejected: Finance only (per-agent settings, every new agent must opt in); an eval exemption (close to the rejected debug switch).
- **Content is everything not on an allowlist.** Kept: span names and types, model name, token counts, durations, tool names and call order, level, exception type, status codes (`agent_run_failed`, `grounding_failure_code`), counts (`citation_count`, `passage_count`, `retrieved_chunk_count`, rerank kept/dropped/failed, memory counts), booleans (`insufficient_evidence`), retrieval settings (`candidate_k`, `top_k`, `rrf_k`, corpus), `user_id` and `session_id` as UUIDs, agent tag, environment. Dropped includes retrieval filters (a sender or ticker says what was asked) and exception messages (validation and API errors quote model output).
- **Local mode replaces Langfuse.** With `local_trace_content` on, full content goes only to a local JSONL file and Langfuse is never constructed in that process. Rejected: both at once with an export-time filter, since privacy would then rest on the filter.
- **Guard on the platform, not only our variable.** Settings refuse `local_trace_content` when `environment == "production"` or `RAILWAY_ENVIRONMENT_NAME` is set. `email-ingest` shows why: it has no `ENVIRONMENT`. Rejected: checking `environment` alone; making `environment` required.
- **Evals: app spans content-free; harness records may keep synthetic content.** The experiment view keeps each case's question, answer and judge reasons; the app's spans under it show shape only. Rejected: content-free experiment records (a table of numbers in Langfuse, larger rework).
- **Plan 003's newsletters are a recorded exception.** `news-extraction-v1/v2` and the extraction mode's experiment records stay as they are. Any new real-data benchmark needs its own decision; invoice content never goes to Langfuse. Rejected: moving the datasets to the private bucket and deleting them from Langfuse.

**The rule:** no app trace in Langfuse carries content. Eval harness records may carry synthetic data, plus plan 003's newsletters.

## Design

```text
                 local_trace_content?
                 ├─ yes ─► instrument_all(content on, binary off) ─► JsonlSpanExporter ─► backend/traces/*.jsonl
                 │         (Langfuse not constructed; Langfuse SDK spans are no-ops)
configure_tracing()
                 ├─ no, Langfuse keys ─► instrument_all(content off, binary off)
                 │                       hand-made spans without input/output content
                 │                       ─► Langfuse(span_exporter=ContentFreeExporter(OTLP)) ─► Langfuse
                 └─ no keys ─► off
```

- **At the source.** `Agent.instrument_all(InstrumentationSettings(include_content=False, include_binary_content=False))`. The hand-made spans drop their content unconditionally: `generate-chat-response` has no input or output (level, status and count metadata stay); `hybrid-search` and `news-search` have no input (settings metadata stays, `passage_count` moves to metadata); `embed-query` has no input (model stays); `rerank` has no input or output, and its candidate, kept, dropped and failed counts go to metadata. No local-mode branches in these spans: in local mode they are no-ops, and PydanticAI's spans already carry the same content (user text, answer, tool arguments with query and filters, tool results with passages).
- **At the boundary.** `ContentFreeExporter` wraps an `OTLPSpanExporter` built as the SDK builds it (`{base_url}/api/public/otel/v1/traces`, Basic auth and `x-langfuse-*` headers) and is passed as `Langfuse(span_exporter=...)`. Per span it keeps only allowlisted attribute keys (never `langfuse.observation.input` or `output`), reduces `exception` events to `exception.type` and drops other events, and replaces the status description with the exception type. The Langfuse experiment harness spans `experiment-item-run` and `experiment-item-task` pass unchanged; they are recognised by name because the experiment attributes propagate to every child span. The email regex is deleted. The allowlist is the "Kept" list as concrete keys, recorded from real content-free spans of PydanticAI 2.46 and Langfuse 4.14.5 in a test. Langfuse's media-upload step runs outside this exporter; `include_binary_content=False` keeps PDFs out of attributes, and a test asserts it.
- **Local mode.** Setting `local_trace_content: bool = False` (`LOCAL_TRACE_CONTENT`), and `railway_environment_name: str | None = None` mirroring Railway's variable. A `model_validator` raises when the setting is on and either guard condition holds, naming both; every process loads settings at import, so the API, the crons and eval commands all refuse. `JsonlSpanExporter` (stdlib `json`, about 30 lines) writes `backend/traces/<UTC timestamp>-<pid>.jsonl`, one line per finished span: `name`, `trace_id`, `span_id`, `parent_id`, `start`, `end` (ISO UTC), `status`, `attributes`, `events`. Behind a `SimpleSpanProcessor`. `backend/traces/` is gitignored; files are never rotated or deleted automatically. Binary content stays out here too: PDFs are in the database and base64 would bloat the file. `shutdown_tracing()` flushes whichever provider is active.
- **Ingest.** `ingest/email/run.py` `main` calls `configure_tracing()` at start and `shutdown_tracing()` in a `finally`, tagging its runs `ingest`. Labelling, news extraction and 001/05's invoice extraction then appear content-free. `email-ingest` on Railway needs the Langfuse keys added (and `ENVIRONMENT=production` for clean filtering); without keys it simply stays untraced.
- **Evals.** With `local_trace_content` on, `eval_tracing()` skips Langfuse; `run_experiment` runs the task over the committed local payloads, computes the same scores, and writes the report with `"published": false, "reason": "local_trace_content"` next to the JSONL trace. The extraction mode refuses local-content runs with a clear message: its cases exist only in Langfuse, and `--replay` with saved runs already covers debugging it. `evals/README.md` states the rule and the plan 003 exception.
- **Finance.** Nothing Finance-specific: 001/05 and 001/12 inherit the global rule. Their "Content-free tracing" scope line becomes a test that the run's exported spans pass the allowlist with no content.
- **Configuration and deployment.** New settings `local_trace_content` and `railway_environment_name`; `LOCAL_TRACE_CONTENT=false` in `backend/.env.example`; Langfuse keys on `email-ingest`. No new dependencies (`OTLPSpanExporter` comes with `langfuse`).

## Success criteria

1. A real chat turn in each agent (Documents, Email) shows in Langfuse with models, tokens, timings and tool names, and no question, answer, query, filter, passage or tool result.
2. A failing turn shows its level, exception type and status code in Langfuse, and no exception message.
3. With `LOCAL_TRACE_CONTENT=true` locally, a chat turn writes a JSONL file containing the question, tool results and answer, and nothing reaches Langfuse.
4. With `LOCAL_TRACE_CONTENT=true`, settings refuse to load under `ENVIRONMENT=production` and under `RAILWAY_ENVIRONMENT_NAME`.
5. A scheduled ingest run on Railway appears in Langfuse, content-free.
6. Eval runs still publish experiments with scores; a local-content retrieval run writes an unpublished report and a JSONL trace.

## Tasks

- [ ] [004/01 — Content-free Langfuse export](tasks/01-content-free-export.md)
- [ ] [004/02 — Local trace content and the production guard](tasks/02-local-trace-content.md) — after 01
- [ ] [004/03 — Email ingest is traced](tasks/03-traced-ingest.md) — after 01
- [ ] [004/04 — Evals under content-free tracing](tasks/04-evals.md) — after 02

```text
01 ─┬─► 02 ─► 04
    └─► 03
```

Finance 001/05 and 001/12 wait on 01, 02 and 03 (extraction runs in ingest).

## Open questions and risks

- **A library upgrade adds a content attribute.** The exporter allowlist drops unknown keys; the cost is that a useful new non-content key is also dropped until added. Next action: the allowlist test in 004/01 fails loudly on a version bump that changes the keys.
- **Langfuse changes its OTLP endpoint or headers.** Building the exporter ourselves means following SDK changes. Next action: 004/01's manual check of a live trace; repeat it on a `langfuse` upgrade.
- **Media upload outside our exporter.** Safe only while binary content is off at the source. Next action: the PDF test in 004/01.
- **Debugging production issues gets harder.** Shape, counts and error types are what remain; reproduce locally with `LOCAL_TRACE_CONTENT`. Next action: none.

# Document Copilot — evals & monitoring build guide

Companion to [todo.md](todo.md), same format. Work top to bottom; each step lists what to do, where it lives, and how to verify before moving on.

**Decision:** [Langfuse](https://langfuse.com) Cloud, Hobby (free) tier. OpenTelemetry-native, so instrumentation is vendor-neutral — swapping the export target later (self-hosted Langfuse, Phoenix, Logfire) is a config change, not a rewrite. `pydantic-evals` (already in the lockfile via `pydantic-ai`'s `evals` extra) is the offline eval runner; Langfuse is where traces, production metrics, and eval scores are viewed.

References: [client-brief.md](../01-document-copilot/client-brief.md) (trust requirements + gold questions), [architecture.md](../01-document-copilot/architecture.md).

---



## What we track in production (via tracing)

All of this falls out of one instrumentation pass — no bespoke metrics code:

- **Latency** — end-to-end turn time and per-span breakdown (embed query → semantic search → FTS → RRF → neighbor hydration → LLM call → tool calls). Real agent wall-time, not time-to-first-byte — the current stream is fake (full answer materializes, then gets chopped into fixed-size frames), so TTFT isn't a meaningful metric here.
- **Cost & token usage** — input/output/cached tokens per call, rolled up per trace/thread/user. Today `app/assistant/agent.py` keeps only 4 of ~9 available `RunUsage` fields and drops usage entirely on both error paths and the grounding-failure path — tracing captures the full picture regardless of which path the turn takes.
- **Error rate** — `AGENT_FAILURES` (LLM/API errors) vs. unexpected exceptions vs. grounding failures, as distinct trace outcomes.
- **Grounding pass rate** — `validate_grounded_answer`'s outcome as a score per trace, broken out by failure code (`missing_citations`, `unknown_chunk`, `duplicate_index`, `insufficient_with_citations`). `unknown_chunk` in particular is a hallucinated-citation signal worth its own alert.
- **Refusal rate** — how often `insufficient_evidence=True` fires, and on what kinds of questions (today this flag is validated but never counted anywhere).
- **Citation count per answer** — thin answers (0–1 citations that still pass validation) vs. well-supported ones.
- **Tool-call shape** — count and order of `search_filings` / `read_chunk` / `read_surrounding_chunks` per turn; flags runaway tool loops (there's currently no `usage_limits` ceiling on the agent).
- **Retrieval candidate set vs. cited set** — `deps.seen_passages` holds everything retrieved (with fusion scores) but only cited chunks reach the DB; tracing is the only place this gap becomes visible after the fact.



## What we evaluate offline (via `pydantic-evals`, scored in Langfuse)

- **Grounding contract** — every case asserts the four `validate_grounded_answer` rules, reusing that validator directly (no LLM judge needed — it's deterministic).
- **Correct refusal** — the Tesla FY2023 question (already in `scripts/smoke_agent.py`) must produce `insufficient_evidence=True` with zero citations; the 10 in-corpus questions must not.
- **No-advice rule** — `instructions.md` says no stock recommendations/price targets; nothing in code enforces this today. Needs an `LLMJudge` evaluator since it's a qualitative prompt rule.
- **Excerpt fidelity** — each citation's `excerpt` should be verbatim-findable in the source chunk text; currently unchecked anywhere.
- **Answer quality on comparison questions** — the multi-year, multi-company questions (e.g. Apple revenue mix 2021–2025) are where a real answer-quality judge earns its cost; sparingly, on a curated subset.
- **(Stretch) Retrieval recall/precision** — needs a hand-labeled question → expected chunk_id set, which doesn't exist yet. Track as a follow-up dataset, not part of the first pass.

---



## Step 1 — Langfuse account + project

- [x] Create a Langfuse Cloud account (EU or US region) — free Hobby tier
- [x] Create a project for Document Copilot
- [x] Generate a public/secret API key pair, scoped to this project
- [x] ~~Note the OTLP endpoint~~ — not needed: the Langfuse Python SDK auto-configures its own OTel export pipeline from `base_url`, no manual OTLP endpoint/header wiring required (see Step 3)

**Verify:** keys exist in the Langfuse dashboard; endpoint reachable with a `curl` auth check.

## Step 2 — Backend config + dependencies

- [x] Add `langfuse` as a direct dependency (`uv add langfuse`) — pulls in `opentelemetry-sdk` / `opentelemetry-exporter-otlp-proto-http` transitively, no need to declare those separately
- [x] Add settings to `app/config.py`: `environment` (`local` / `production`), `langfuse_public_key`, `langfuse_secret_key`, `langfuse_base_url` — blank keys mean tracing is silently disabled (fail-open, not fail-fast, since Langfuse isn't required for the app to function)
- [x] Add the three vars to `backend/.env.example` and local `.env`
- [ ] Add the same vars to the Railway backend service env — do before deploying; local-only so far

**Verify:** `uv run python -c "from app.config import settings; print(settings.langfuse_base_url)"` succeeds locally; add to Railway before deploy.

## Step 3 — Instrument the agent

- [x] In `app/observability.py` (new module), call `Agent.instrument_all()` at startup — PydanticAI emits OTel spans natively (tool calls, model calls, token usage) with no manual span code
- [x] ~~Initialize the OTel `TracerProvider` + OTLP HTTP exporter manually~~ — superseded: `Langfuse(...)` auto-configures OTel export when constructed; wired into `app/main.py` between `configure_logging()` and `app = FastAPI(...)`. One catch found and fixed: PydanticAI's instrumentation reads the OTel *global* tracer provider, so our custom provider (below) must be registered globally via `trace.set_tracer_provider()` *before* handing it to `Langfuse()`, or agent spans silently stop exporting.
- [x] Set `service.name` resource attribute (`document-copilot-backend`) and an `environment` attribute (`local` / `production`) so Langfuse can filter by env — verified live: `resourceAttributes.service.name` now reads `document-copilot-backend` instead of `unknown_service`
- [x] Made retrieval visible as its own spans: `app/retrieval/retriever.py` now wraps hybrid search in a `retriever`-typed observation (query, filters, candidate/top/rrf-k, passage count, tickers) and the OpenAI embedding call in an `embedding`-typed observation — this wasn't in the original plan but directly satisfies the "nested spans for retrieval" verify line below; previously the whole `search_filings` tool call was one opaque ~10s block
- [x] Converted `app/chat/titles.py` off the raw `openai.OpenAI` client onto a small PydanticAI `Agent` (`output_type=ThreadTitle`) — the thread-naming call is now traced automatically instead of being invisible; same fallback behavior on failure, now catching PydanticAI's exception types
- [ ] **Skipped, deliberately:** `FastAPIInstrumentor` / `HTTPXClientInstrumentor` for HTTP/DB-level spans (Supabase Auth, `search_filings`'s remaining raw-httpx calls in `ingest/embeddings.py`'s FTS keyword extraction). Reason found while implementing: Langfuse v4's default `should_export_span` filter only forwards Langfuse-SDK spans and spans carrying `gen_ai.*` attributes — plain HTTP/DB spans from these instrumentations would be created but silently dropped before export unless `should_export_span` is also overridden to include them. Doing that turns on exactly the "HTTP spans, database queries... clutter" the Langfuse best-practices doc warns against. Revisit only if step-level DB/auth latency becomes something we actually need to see.
- [x] Added a `shutdown_tracing()` call on `@app.on_event("shutdown")` (left `startup` as-is per the note below) that flushes buffered spans via `get_client().shutdown()` before process exit, since Railway can SIGTERM mid-request

**Verify:** run one chat turn locally, confirm a trace appears in the Langfuse UI within ~1 minute with nested spans for retrieval, tool calls, and the LLM call. — **Done**, confirmed live via `langfuse-cli`:
```
generate-chat-response (SPAN, root)
├─ document-copilot run (AGENT)
│  ├─ chat gpt-5.5 (GENERATION)
│  ├─ search_filings (TOOL)
│  │  └─ hybrid-search (RETRIEVER)
│  │     └─ embed-query (EMBEDDING)
│  ├─ chat gpt-5.5 (GENERATION)
│  ├─ read_chunk (TOOL) ×2
│  └─ chat gpt-5.5 (GENERATION)
└─ thread-title run (AGENT)
   └─ chat gpt-5.5 (GENERATION)
```

## Step 4 — Capture what's currently discarded

- [ ] In `app/assistant/agent.py::run_agent`, widen the `usage` dict to include `cache_read_tokens`, `cache_write_tokens`, `details` from `RunUsage` — cheap to add now that it's about to be visible in dashboards
- [ ] In `app/chat/orchestrator.py`, attach `usage` on the grounding-failure persistence path too (currently hardcoded to `None` at the `except GroundingError` branch) — tokens spent on a rejected answer are exactly the population cost dashboards need
- [ ] Bind `thread_id` and `user_id` as OTel/Langfuse trace attributes (via `langfuse_context`/span attributes, or plain OTel `set_attribute`) so traces are filterable per analyst and per thread — `user_id` on `DocumentAgentDeps` is currently set but never read anywhere
- [ ] Tag each trace with the loaded prompt version — hash or mtime of `instructions.md` at `get_agent()` construction time — so eval regressions can be attributed to a specific prompt revision later

**Verify:** a trace in Langfuse shows `thread_id`, `user_id`, cache token fields, and a prompt-version tag; a manually triggered grounding failure still shows non-null usage.

## Step 5 — Wire grounding as a Langfuse score

- [ ] In `app/chat/orchestrator.py`, after `validate_grounded_answer` succeeds or raises `GroundingError`, emit a Langfuse score on the current trace: `grounded` (boolean) and, on failure, `grounding_failure_code` (string: `missing_citations` / `unknown_chunk` / `duplicate_index` / `insufficient_with_citations`)
- [ ] Emit a second score for `insufficient_evidence` (the self-reported abstention flag) so refusal rate becomes queryable without re-deriving it from citation count
- [ ] Emit `citation_count` as a numeric score for the thin-answer signal

**Verify:** Langfuse trace detail view shows all three scores after a real chat turn; a Langfuse dashboard chart can group traces by `grounding_failure_code`.

## Step 6 — Offline eval harness (`pydantic-evals`)

- [ ] Create `backend/evals/` (new top-level dir, sibling to `app/`, `ingest/`, `tests/` — kept out of `pytest -m "not integration"` since it hits OpenAI + Postgres)
- [ ] Build the seed dataset as a `pydantic_evals.Dataset` from the 10 client-brief questions + the Tesla refusal case already enumerated in `scripts/smoke_agent.py`, with expected `insufficient_evidence` per case
- [ ] Add evaluators:
  - custom `Evaluator` wrapping `validate_grounded_answer` (reuse, don't reimplement)
  - `EqualsExpected` on `insufficient_evidence`
  - `MaxToolCalls` / `MaxDuration` as regression guards
  - `LLMJudge` for the no-advice rule, scoped narrowly to that one rule
- [ ] Add a `report_to_langfuse` step (or plain OTel export from the eval run) so eval scores land in the same Langfuse project as production traces, tagged `source=eval` vs `source=production`
- [ ] Delete or fold `scripts/smoke_agent.py` into this once the dataset supersedes it — it's the closest existing thing to an eval harness today

**Verify:** `uv run python -m evals.run_agent_evals` (or equivalent) produces a scored report locally; the same run's traces and scores appear in Langfuse tagged `source=eval`.

## Step 7 — Dashboards + alerting

- [ ] In Langfuse, build a dashboard: grounding pass rate, refusal rate, p50/p95 latency, cost per day, `unknown_chunk` rate (hallucinated-citation proxy)
- [ ] Set a Langfuse alert (or manual weekly check on Hobby tier, which may not include alerting) on `unknown_chunk` rate crossing a threshold — this is the single most trust-relevant regression signal per the client brief's "never invent facts" requirement
- [ ] Confirm 30-day retention on the Hobby tier is acceptable; screenshot/export any trace worth keeping long-term for portfolio purposes before it ages out

**Verify:** dashboard renders with at least one day of real or eval-generated traffic; alert (or manual check) is documented.

## Step 8 — Docs

- [ ] Add a short "Observability" section to [README.md](../../README.md) — env vars required, how to view traces, how to run evals
- [ ] Update `AGENTS.md` / `backend/AGENTS.md` if the eval-run command becomes part of the standard pre-merge checklist

**Verify:** a fresh clone + `.env` fill-in gets someone from zero to seeing their first trace in Langfuse, following only the README.

---



## Out of scope — do not build (for this pass)

- Self-hosted Langfuse (Hobby cloud tier covers this project's scale)
- A second observability tool (Phoenix, Logfire APM) alongside Langfuse
- Automated retrieval recall/precision evals — needs a labeled dataset that doesn't exist yet; track as a future step once the production trace data can seed it
- Infra-level APM (DB/Supabase Auth latency, uvicorn metrics) — out of Langfuse's scope and not needed at this project's scale

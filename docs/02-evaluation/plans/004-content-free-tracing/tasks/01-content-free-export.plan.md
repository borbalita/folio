# 004/01 Content-free Langfuse export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No app span exported to Langfuse carries content; spans keep models, tools, tokens, timings, counts and error types.

**Architecture:** Two layers. At the source, PydanticAI instrumentation runs with content and binary content off, and the hand-made Langfuse spans stop passing content. At the boundary, `ContentFreeExporter` wraps the OTLP exporter handed to `Langfuse(span_exporter=...)` and rebuilds every span from an allowlist. The two Langfuse experiment harness spans pass through unchanged.

**Tech Stack:** pydantic-ai-slim 2.46.0, langfuse 4.14.5, opentelemetry-sdk 1.44.0, pytest.

**Spec:** [README.md](../README.md), task [01-content-free-export.md](01-content-free-export.md).

## Global Constraints

- No new dependencies. `OTLPSpanExporter` (`opentelemetry.exporter.otlp.proto.http.trace_exporter`) comes with `langfuse`.
- Content is everything not on the allowlist. Retrieval filter values and exception messages are content.
- Harness records keep their content: spans named `experiment-item-run` and `experiment-item-task` pass through unchanged.
- `uv run pytest -m "not integration"` and `uv run ruff check .` pass from `backend/`.

## Findings that shape this plan (probed 2026-10-09)

- `InstrumentationSettings(include_content=False, include_binary_content=False)`, set through `Agent.instrument_all(...)` (`Agent(...)` has no `instrument=` argument in 2.46), already strips prompts, instructions, outputs, tool arguments and results, and PDF bytes. Message attributes keep structure only (part types, tool names, MIME type), and exception events keep only `exception.type`.
- Langfuse SDK spans (`start_as_current_observation`) store content in `langfuse.observation.input`/`output`. When one raises, it exports `exception.message`, `exception.stacktrace`, and a status description of `"<Type>: <message>"`. `mask_otel_spans` cannot reach events or status, hence the exporter.
- The experiment attributes (`langfuse.experiment.*`) are propagated to every child span, so harness spans are recognised by name, not by attribute.
- `get_client()` returns a disabled client when more than one Langfuse instance exists. Importing `app.main` in tests runs `configure_tracing()`, so tests patch `get_client` in each module rather than relying on the global client.

## Review Focus

1. **A Langfuse span that raises inside search or rerank** (a DB or TypeSafe error whose message holds the query): only the exception type may be exported. Task 1, `test_exception_events_keep_only_the_type`.
2. **The failing chat turn:** `generate-chat-response` with level ERROR keeps `agent_run_failed`, and the status description must not become the exception text. Task 1, `test_status_description_is_the_exception_type_or_the_status_code`.
3. **Eval runs:** the harness spans keep their input and output while app spans under them lose theirs. Task 1, `test_experiment_harness_spans_pass_unchanged`.
4. **A span with no exporter-relevant attributes** (a plain OTel span from some library) must still export, without crashing. Task 1, `test_unknown_keys_are_dropped`.
5. **Rerank counts** must still appear after `input`/`output` are removed. Task 3, `test_rerank_span_keeps_counts_not_query`.

---

### Task 1: `ContentFreeExporter`

**Files:**
- Create: `backend/app/trace_export.py`
- Test: `backend/tests/test_trace_export.py`

**Interfaces:**
- Produces:
  - `class ContentFreeExporter(SpanExporter)` with `__init__(self, inner: SpanExporter)`; `export`, `shutdown` and `force_flush` delegate to `inner` after filtering.
  - `def content_free(span: ReadableSpan) -> ReadableSpan`.
  - `def langfuse_otlp_exporter(public_key: str, secret_key: str, base_url: str | None) -> OTLPSpanExporter`.
  - Constants `HARNESS_SPANS`, `ALLOWED_KEYS`, `ALLOWED_PREFIXES`, `ALLOWED_METADATA`.

**Allowlist (exact values):**

```python
HARNESS_SPANS = frozenset({"experiment-item-run", "experiment-item-task"})
ALLOWED_KEYS = frozenset({
    # PydanticAI (gen_ai conventions)
    "gen_ai.operation.name", "gen_ai.system", "gen_ai.provider.name",
    "gen_ai.request.model", "gen_ai.response.model", "gen_ai.agent.name",
    "gen_ai.agent.call.id", "gen_ai.conversation.id", "gen_ai.tool.name",
    "gen_ai.tool.call.id", "agent_name", "model_name",
    # Langfuse
    "user.id", "session.id", "langfuse.environment", "langfuse.trace.name",
    "langfuse.trace.tags", "langfuse.observation.type", "langfuse.observation.level",
    "langfuse.observation.status_message", "langfuse.observation.model.name",
    "langfuse.observation.usage_details", "langfuse.internal.is_app_root",
    "langfuse.internal.as_root", "langfuse.experiment.id", "langfuse.experiment.name",
    "langfuse.experiment.item.id", "langfuse.experiment.item.root_observation_id",
    "langfuse.experiment.dataset.id",
})
ALLOWED_PREFIXES = ("gen_ai.usage.", "gen_ai.aggregated_usage.")
ALLOWED_METADATA = frozenset({
    "citation_count", "insufficient_evidence", "retrieved_chunk_count",
    "grounding_failure_code", "passage_count", "corpus", "candidate_k", "top_k",
    "rrf_k", "model", "candidates", "kept", "dropped", "failed",
})  # exported as "langfuse.observation.metadata.<name>"
```

Deliberately not allowed: `gen_ai.input.messages`, `gen_ai.output.messages`, `pydantic_ai.all_messages`, `gen_ai.tool.definitions`, `model_request_parameters`, `logfire.*`, and `langfuse.observation.input`/`output`. The message attributes are structure-only today, but the backstop must not trust the source.

- [ ] **Step 1: Write the failing tests** in `tests/test_trace_export.py`. Build spans with an SDK `TracerProvider` and `InMemorySpanExporter`, then pass the finished spans through `content_free`, or export them through `ContentFreeExporter(InMemorySpanExporter())`.
  - `test_allowed_keys_and_metadata_survive`: a span with `gen_ai.request.model="gpt-x"`, `gen_ai.usage.input_tokens=5`, `langfuse.observation.metadata.citation_count=2` and `user.id="u"` keeps all four, with their values.
  - `test_content_keys_are_dropped`: a span with `langfuse.observation.input="SECRET"`, `langfuse.observation.output="SECRET"`, `langfuse.observation.metadata.filters='{"sender":"SECRET"}'` and `gen_ai.input.messages="SECRET"` exports no attribute whose value contains `"SECRET"`.
  - `test_unknown_keys_are_dropped`: `foo.bar="x"` is absent; the span still exports, with its name, ids and timings unchanged.
  - `test_exception_events_keep_only_the_type`: a span that records `RuntimeError("SECRET")` has exactly one event, `exception`, with attributes `{"exception.type": "RuntimeError"}`. Other events are dropped.
  - `test_status_description_is_the_exception_type_or_the_status_code`: (a) an error span with an exception has description `"RuntimeError"`; (b) an error span with no exception and `langfuse.observation.status_message="agent_run_failed"` has description `"agent_run_failed"`; (c) otherwise the description is `None`. Status codes are unchanged.
  - `test_experiment_harness_spans_pass_unchanged`: a span named `experiment-item-run` with `langfuse.observation.input="ITEM"` keeps it. A child named `app-span` with the same experiment attributes loses its input but keeps `langfuse.experiment.item.id`.
  - `test_langfuse_otlp_exporter_matches_the_sdk`: the endpoint is `"https://cloud.langfuse.com/api/public/otel/v1/traces"` when `base_url` is `None`, otherwise `f"{base_url}/api/public/otel/v1/traces"`. `Authorization` is `"Basic " + b64("pk:sk")`, and `x-langfuse-public-key` is set.

- [ ] **Step 2: Run them to see them fail.** Run `uv run pytest tests/test_trace_export.py -q`. Expected: an ImportError on `app.trace_export`.

- [ ] **Step 3: Implement `app/trace_export.py`.**
  - `content_free` returns the span unchanged when its name is in `HARNESS_SPANS`. Otherwise it returns a new `ReadableSpan` with the same name, context, parent, resource, kind, times and instrumentation scope; filtered attributes; events reduced to `Event("exception", {"exception.type": ...}, timestamp)` (other events dropped); no links; and `Status(code, description)` following the rule in the test.
  - `langfuse_otlp_exporter` copies the headers and endpoint from `langfuse/_client/span_processor.py` (lines 101–129), including `x-langfuse-sdk-name` and `x-langfuse-sdk-version` from `langfuse._version.__version__`.

- [ ] **Step 4: Run them to see them pass.** Run `uv run pytest tests/test_trace_export.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.** `feat(tracing): content-free span exporter with an allowlist (004/01)`.

### Task 2: Content-free configuration in `observability.py`

**Files:**
- Modify: `backend/app/observability.py` (delete `_EMAIL_PATTERN` and `_mask_otel_spans`; change `configure_tracing`)
- Test: `backend/tests/test_observability.py`

**Interfaces:**
- Consumes: `ContentFreeExporter` and `langfuse_otlp_exporter` from Task 1.
- Produces: `CONTENT_FREE = InstrumentationSettings(include_content=False, include_binary_content=False)` (module constant). `configure_tracing()` keeps its signature, calls `Agent.instrument_all(CONTENT_FREE)`, and constructs `Langfuse(..., span_exporter=ContentFreeExporter(langfuse_otlp_exporter(...)), tracer_provider=provider)` without `mask_otel_spans`. 004/02 adds the local mode.

- [ ] **Step 1: Write the failing tests** in `tests/test_observability.py`. The fixture builds a `TracerProvider` with `SimpleSpanProcessor(ContentFreeExporter(InMemorySpanExporter()))` and calls `Agent.instrument_all(InstrumentationSettings(include_content=False, include_binary_content=False, tracer_provider=tp))`. It restores `Agent.instrument_all(False)` afterwards.
  - `test_agent_run_exports_shape_not_content`: a `FunctionModel` agent with `instructions="SECRET-INSTR"` calls a tool `search(query)` with `"SECRET-QUERY"`; the tool returns `"SECRET-RESULT"`; the final text is `"SECRET-ANSWER"`. The run gets `["SECRET-USER", BinaryContent(b"%PDF-SECRET", media_type="application/pdf")]`. No exported attribute, event or status contains any `SECRET-` string or `"PDF"`. `gen_ai.request.model`, `gen_ai.usage.input_tokens` and `gen_ai.tool.name == "search"` are present.
  - `test_failing_agent_exports_the_type_only`: a `FunctionModel` raising `ValueError("SECRET-ERROR")` produces an `exception` event with only `exception.type == "ValueError"`, and `"SECRET-ERROR"` appears nowhere.
  - `test_configure_tracing_uses_content_free_settings`: monkeypatch the settings with Langfuse keys, and patch `Langfuse` and `Agent.instrument_all` in `app.observability` with recorders. After `configure_tracing()`, `instrument_all` received `CONTENT_FREE`, and `Langfuse` received a `ContentFreeExporter` as `span_exporter` and no `mask_otel_spans`.

- [ ] **Step 2: Run them to see them fail.** Run `uv run pytest tests/test_observability.py -q`. Expected: ImportError for `CONTENT_FREE`, or a failed assertion.

- [ ] **Step 3: Change `configure_tracing`** as described in Interfaces. Update the module docstring to say the export is content-free for every agent.

- [ ] **Step 4: Run them to see them pass,** together with `tests/test_trace_export.py`.

- [ ] **Step 5: Commit.** `feat(tracing): content-free instrumentation for every agent (004/01)`.

### Task 3: Hand-made spans without content

**Files:**
- Modify: `backend/app/chat/orchestrator.py:238-320`, `backend/app/retrieval/base.py:41-82`, `backend/app/retrieval/news/retriever.py:96-124`, `backend/app/retrieval/email/rerank.py:76-100`
- Modify: `backend/tests/conftest.py` (fixture)
- Test: `backend/tests/chat/test_orchestrator.py`, `backend/tests/retrieval/test_base.py`, `backend/tests/retrieval/email/test_email_rerank.py`, `backend/tests/retrieval/news/` (the existing news retriever test file, or `test_news_retriever.py`)

**Interfaces:**
- Consumes: `ContentFreeExporter` (Task 1).
- Produces: fixture `langfuse_spans(monkeypatch) -> InMemorySpanExporter`. It builds `Langfuse(public_key="pk-test", secret_key="sk-test", base_url="http://127.0.0.1:9", span_exporter=ContentFreeExporter(InMemorySpanExporter()), tracer_provider=TracerProvider())`, monkeypatches `get_client` in `app.chat.orchestrator`, `app.retrieval.base`, `app.retrieval.news.retriever` and `app.retrieval.email.rerank` to return it, and yields the inner in-memory exporter (call `flush()` before reading).

Span changes (exact):
- `generate-chat-response`: no `input=` and no `output=` in any `update`. Level, status message and metadata stay.
- `hybrid-search` / `news-search`: no `input=`. `passage_count` moves from `output=` to `metadata=`. `_span_output` is renamed `_span_metadata` and returns the same dict, including the documents subclass override.
- `embed-query`: no `input=`; `model=` stays.
- `rerank`: no `input=`; metadata gains `"candidates": len(passages)`. The final `update` passes `metadata={"kept": ..., "dropped": ..., "failed": ...}` instead of `output=`.

- [ ] **Step 1: Write the failing tests,** each using `langfuse_spans`.
  - `test_orchestrator.py::test_turn_span_has_no_question_or_answer`: run the existing happy-path setup with user text `"SECRET-Q"` and answer `"SECRET-A"`. The `generate-chat-response` span has no attribute containing either string, and `langfuse.observation.metadata.citation_count` is present.
  - `test_orchestrator.py::test_failed_turn_span_keeps_the_code_not_the_message`: the agent raises `ModelHTTPError` with body `"SECRET"`. The span has level `ERROR`, status message `agent_run_failed`, and no `SECRET`.
  - `test_base.py::test_search_span_has_settings_not_query`: query `"SECRET-Q"` with a filter value `"SECRET-F"`. The `hybrid-search` and `embed-query` spans carry neither; `top_k` and `passage_count` metadata are present.
  - The news retriever test file gets the same test for `news-search`.
  - `test_email_rerank.py::test_rerank_span_keeps_counts_not_query`: query `"SECRET-Q"` and question `"SECRET-QQ"`. The `rerank` span has metadata `candidates`, `kept`, `dropped` and `failed`, and neither string.

- [ ] **Step 2: Run them to see them fail.** Expected: the `SECRET` assertions fail where input or output are set today, and the metadata assertions fail for `passage_count`, `candidates` and `kept`.

- [ ] **Step 3: Make the span changes** listed above.

- [ ] **Step 4: Run the full fast suite.** Run `uv run pytest -m "not integration" -q && uv run ruff check .` from `backend/`. Expected: all pass, and ruff is clean.

- [ ] **Step 5: Commit.** `feat(tracing): hand-made spans carry counts, not content (004/01)`.

### Task 4: Docs, live check, verification record

**Files:**
- Modify: `docs/02-evaluation/legacy/evals-todo.md` (Steps 3 and 5)
- Modify: `docs/02-evaluation/plans/004-content-free-tracing/tasks/01-content-free-export.md` (link this plan; add `Verified`)
- Modify: `docs/02-evaluation/plans/004-content-free-tracing/README.md` (Status `In progress`; tick 004/01 once every criterion passes)

- [ ] **Step 1: Docs.** In `evals-todo.md` Step 3, add one line: trace input and output are content-free since plan 004, so nested spans show shape only. In Step 5, add one line: scores and counts are the signal, not text. Link this plan from the task file's Notes.

- [ ] **Step 2: Live check (manual).** Run the backend locally with Langfuse keys and send one Documents and one Email turn from the browser. In Langfuse, the traces show nested agent, tool, generation and search spans, with model, tokens, tool names and counts, and no question, answer, query or passage. Ask the owner to confirm in the Langfuse UI too.

- [ ] **Step 3: Record.** Add a `Verified` section to the task file (date, one line per acceptance criterion with how it was checked, PR link). Set the spec's status to `In progress`, and tick 004/01 only if every criterion passed.

- [ ] **Step 4: Commit and open the PR** against `main`. The PR description lists the three remaining tasks and notes that Langfuse traces from before the deploy still hold content.

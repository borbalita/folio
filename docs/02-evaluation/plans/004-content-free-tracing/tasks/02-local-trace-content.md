# 004/02 — Local trace content and the production guard

## Goal
With a local-only setting on, full trace content goes to a local file and nowhere else; the setting cannot load on Railway or in production.

## Scope
- Settings `local_trace_content: bool = False` and `railway_environment_name: str | None = None` (mirrors `RAILWAY_ENVIRONMENT_NAME`).
- A `model_validator` that raises when `local_trace_content` is on and either `environment == "production"` or `railway_environment_name` is set; the message names both.
- `configure_tracing()` picks one mode: local content (global provider, `SimpleSpanProcessor(JsonlSpanExporter)`, `instrument_all(include_content=True, include_binary_content=False)`, Langfuse never constructed), Langfuse (004/01), or off.
- `JsonlSpanExporter` writes `backend/traces/<UTC timestamp>-<pid>.jsonl`, one line per finished span: `name`, `trace_id`, `span_id`, `parent_id`, `start`, `end`, `status`, `attributes`, `events`. Stdlib only.
- `shutdown_tracing()` flushes the active provider in either mode.
- `backend/traces/` in `.gitignore`; `LOCAL_TRACE_CONTENT=false` with a one-line comment in `backend/.env.example`; a short "Seeing content locally" paragraph in `docs/00-guides/backend-setup.md`.

## Out of scope
- Eval commands in local mode (004/04).

## Acceptance criteria
- Given `local_trace_content` on and `environment=production`, when settings load, then they raise. (test)
- Given `local_trace_content` on and `RAILWAY_ENVIRONMENT_NAME` set, when settings load, then they raise. (test)
- Given `local_trace_content` on and Langfuse keys set, when a mocked agent turn runs, then the JSONL file holds the user text, tool result and answer, and Langfuse is never constructed. (test)
- Given `LOCAL_TRACE_CONTENT=true` locally, when one chat turn runs in the browser, then a JSONL file appears with the question and answer, and no new trace appears in Langfuse. (browser)

## Dependencies
004/01.

## Notes
- Decisions: local mode replaces Langfuse rather than running beside it; the guard also checks Railway's own variable because `email-ingest` has no `ENVIRONMENT`.

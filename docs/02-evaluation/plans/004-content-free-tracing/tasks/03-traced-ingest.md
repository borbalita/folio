# 004/03 — Email ingest is traced

## Goal
Email ingest's LLM calls (labelling, news extraction, and later invoice extraction) appear in Langfuse, content-free.

## Scope
- `ingest/email/run.py` `main` calls `configure_tracing()` after logging is set up and `shutdown_tracing()` in a `finally`, for manual and `--scheduled` runs; ingest traces are tagged `ingest`.
- Railway `email-ingest`: add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` and `ENVIRONMENT=production` (the owner sets them).

## Out of scope
- Tracing raw OpenAI SDK calls (embeddings).

## Acceptance criteria
- Given an ingest run, when it ends normally or raises, then tracing was configured and flushed. (test)
- Given the next scheduled run on Railway after the variables are set, when it has new mail, then Langfuse shows its labelling or extraction spans tagged `ingest`, with models and tokens and no email text. (manual)

## Dependencies
004/01.

## Notes
- Without Langfuse keys ingest stays untraced, as today.
- Implementation plan: [03-traced-ingest.plan.md](03-traced-ingest.plan.md).

## Verified

2026-10-14, branch `feat/traced-ingest`.

- Ingest run ends normally or raises → tracing configured and flushed: `test_run_is_traced_and_flushed` (manual and `--scheduled`) and `test_failed_run_still_flushes_tracing`. Pass. Both also check that the run executes inside `propagate_attributes(tags=["ingest"])`.
- Exported spans carry the tag and no content: a PydanticAI `TestModel` run inside that context, exported through `ContentFreeExporter` to an in-memory exporter, gave `chat test` and `invoke_agent agent` spans with `langfuse.trace.tags = ("ingest",)` and neither the prompt nor the output text in any attribute.
- Suite: `uv run pytest -m "not integration"` (with `EMAIL_RERANK=false`, as CI runs it): 416 passed. `ruff check` is clean.
- Railway, labelling or extraction spans tagged `ingest` with models and tokens and no email text: **pending.** Needs the owner to add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` and `ENVIRONMENT=production` to the `email-ingest` service, then a scheduled run with new mail.

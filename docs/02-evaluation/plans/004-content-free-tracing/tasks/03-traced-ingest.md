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

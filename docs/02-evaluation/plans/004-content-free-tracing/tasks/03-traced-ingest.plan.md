# 004/03 — Email ingest is traced: implementation plan

Task: [03-traced-ingest.md](03-traced-ingest.md). Spec: [README](../README.md), Design → Ingest.

**Goal:** every email ingest run, manual or `--scheduled`, configures content-free tracing at start, tags its LLM spans `ingest`, and flushes in a `finally`.

**Approach:** `ingest/email/run.py` `main` calls `configure_tracing()` right after `configure_logging()`, then runs the rest inside `try: with propagate_attributes(tags=["ingest"]) ... finally: shutdown_tracing()`. `propagate_attributes` only touches the OTel context, so it is a no-op without Langfuse keys; `configure_tracing` and `shutdown_tracing` already return early without keys. No changes to `observability.py`, which 004/02 is changing in parallel.

## Steps

1. **Red.** In `tests/ingest/email/test_run.py`, the `scheduled_env` fixture replaces `configure_tracing`, `shutdown_tracing` and `propagate_attributes` in `ingest.email.run` with recorders. New tests:
   - a manual run and a scheduled run each configure tracing once, run inside the `ingest` tag, and shut tracing down once;
   - a scheduled run whose fetch raises still shuts tracing down, and the error propagates.
   Run `uv run pytest tests/ingest/email/test_run.py -m "not integration"`: the new tests fail.
2. **Green.** Change `main` as above. Rerun: all pass.
3. **Check.** `uv run pytest -m "not integration"`, `uv run ruff check .`.
4. **Docs.** Task file: link this plan, add Verified. Plan README: tick 004/03 once the manual criterion passes. The Railway variables on `email-ingest` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`, `ENVIRONMENT=production`) are set by the owner.

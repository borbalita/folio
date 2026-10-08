# 001/02 — Scheduled email ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m ingest.email --scheduled` runs every 30 minutes as a Railway cron service, fetches from one day before the mailbox's last sync, and logs every run in a `job_runs` table.

**Architecture:**
- A generic `job_runs` table plus a `run_job(job, work)` helper. It inserts a `running` row, calls `work()`, and then sets `ok` with the returned counts, or `failed` with the error and re-raises. The row is written in its own session, so a rolled-back ingest session can't lose it. 001/08's bank sync reuses this helper.
- `ingest.email.run` gets a `--scheduled` flag. It reads the mailbox's `last_synced_at`, works out the IMAP `SINCE` date, fetches with no cap, and runs the existing pipeline inside `run_job("email_ingest", ...)`. Overlap is handled by the existing skip rule (`ingest_action`).
- A Railway config file `backend/railway.email-ingest.json` holds the start command and the cron schedule. The cron service points its config-file path at it, because the backend's `railway.json` would otherwise give it the API's uvicorn start command and healthcheck.

**Tech Stack:** Python 3.12, SQLAlchemy + Alembic, pytest, Railway config-as-code.

**Spec:** [../README.md](../README.md) (Decisions: "Email ingest every 30 minutes … as Railway cron (UTC)"; Design: job-run log, RLS), task [02-scheduled-email-ingest.md](02-scheduled-email-ingest.md).

## Global Constraints

- Schedule `*/30 * * * *`, UTC. No lock: Railway skips a run while the previous one is active.
- Scheduled mode: no item cap (`limit=0`). `since` = (`last_synced_at` − 1 day) as a UTC date, or today (UTC) − 7 days when `last_synced_at` is `None` or there is no mailbox row yet.
- Job-run row fields: job name, start, end, status, counts, error. Status is one of `running`, `ok`, `failed`.
- Every new table enables RLS in its migration and is listed in that migration's `RLS_TABLES` (`tests/database/test_rls_migration.py`).
- The new migration revises `ba98a3ea5b4f` (current head on `feat/finance-bank-connection`), so there is a single head.
- **Migration is hand-written:** the dev database is at `c3f1d9a47b20`, behind head, so `alembic revision --autogenerate` refuses to run. Write it in autogenerate's style (`op.create_table` with matching column types and constraint names). Do **not** run `alembic upgrade`; that needs the owner's OK.
- No `.env` reads. No new dependencies.
- Manual mode (`python -m ingest.email` without `--scheduled`) behaves as before: default `--limit 5`, optional `--since`, and no job-run row.

## Review Focus

1. **The run fails partway** (IMAP login error, DB error mid-ingest). The job row ends `failed` with `"<ExceptionType>: <message>"`, the process exits non-zero so Railway marks the run failed, and `last_synced_at` is not advanced, so the next run re-fetches. (Task 1: `run_job` re-raises; Task 2: `main` lets it propagate.)
2. **First run ever: no mailbox row.** Scheduled mode creates the mailbox via `upsert_yahoo_mailbox` before computing `since` and fetches 7 days. (Task 2 test.)
3. **`--scheduled` combined with `--limit` or `--since`.** A silent mix would cap or shift a scheduled run, so it's rejected with an argparse error (exit 2). (Task 2 test.)
4. **A very long error message** (e.g. a big DB error) is truncated to 2000 characters before it's stored. (Task 1 test.)
5. **A `last_synced_at` near midnight UTC.** The date is taken from the UTC value minus one day, so e.g. `2026-10-08 00:30Z` gives `2026-10-07`. (Task 2 test.)

Known gap, accepted: if Railway kills the process outright, its row stays `running`. That's visible in the log, and the next run proceeds normally.

---

### Task 1: `job_runs` table and `run_job` helper

**Files:**
- Create: `backend/app/database/models/job_run.py`
- Modify: `backend/app/database/models/__init__.py` (import + `__all__`)
- Create: `backend/alembic/versions/<rev>_add_job_runs.py` (`down_revision = "ba98a3ea5b4f"`, `RLS_TABLES = ("job_runs",)`, RLS loop and comment as in `ba98a3ea5b4f`)
- Create: `backend/app/database/job_runs.py`
- Test: `backend/tests/database/test_job_runs.py`

**Interfaces:**
- Produces:
  - `class JobStatus(StrEnum)`: `RUNNING = "running"`, `OK = "ok"`, `FAILED = "failed"`.
  - Model `JobRun`, table `job_runs`: `id` UUID PK default `uuid4`; `job` `String(64)` not null; `started_at` timestamptz not null, server default `now()`; `finished_at` timestamptz nullable; `status` `String(16)` not null; `counts` JSONB nullable; `error` Text nullable. Check constraint `ck_job_runs_status` built from `JobStatus` (same pattern as `ck_mailboxes_provider`). Index `ix_job_runs_job_started_at` on (`job`, `started_at`).
  - `run_job(job: str, work: Callable[[], dict[str, Any]], *, open_session: Callable[[], Session] = <get_session_factory()()>) -> dict[str, Any]` in `app/database/job_runs.py`. It opens its own session, adds a `RUNNING` row and commits, then calls `work()`. On success it sets `OK`, `counts`, `finished_at` and returns the counts. On `Exception` it sets `FAILED`, `error = f"{type(exc).__name__}: {exc}"[:2000]`, `finished_at` and commits, then re-raises. It always closes the session. `finished_at` is `datetime.now(UTC)`.

- [ ] **Step 1: Write failing tests** in `tests/database/test_job_runs.py`. Use a small fake session (`add`, `commit`, `close`, recording added rows and the commit count), like `_MemorySession` in `tests/ingest/email/test_pipeline.py`:
  - `test_successful_run_records_ok_and_counts`: `run_job("email_ingest", lambda: {"new": 2})` returns `{"new": 2}`. Exactly one `JobRun` was added, with `job == "email_ingest"`, `status == "ok"`, `counts == {"new": 2}`, `finished_at` set and `error is None`. The session is closed.
  - `test_failed_run_records_error_and_reraises`: `work` raises `RuntimeError("imap down")`. `pytest.raises(RuntimeError)`. The single row has `status == "failed"`, `error == "RuntimeError: imap down"`, `counts is None` and `finished_at` set. The session is closed.
  - `test_running_row_is_committed_before_work`: inside `work`, assert the fake session has already committed once and the row's status is `"running"`.
  - `test_long_error_is_truncated`: an error message of 5000 chars gives `len(row.error) == 2000`.
- [ ] **Step 2: Run** `uv run pytest tests/database/test_job_runs.py -v`. Expected: FAIL (import error).
- [ ] **Step 3: Implement** the model, the `__init__` export, the helper and the migration (columns, check constraint and index exactly as above; downgrade drops the index and the table).
- [ ] **Step 4: Run** `uv run pytest tests/database -v` → PASS, including `test_every_model_table_gets_rls`. Run `uv run alembic heads` → exactly one head, the new revision.
- [ ] **Step 5: Commit** `feat(ingest): job_runs table and run_job helper (001/02)`.

### Task 2: Scheduled mode and Railway cron config

**Files:**
- Modify: `backend/ingest/email/run.py`
- Create: `backend/railway.email-ingest.json`
- Modify: `README.md` § Deploy (add an `email-ingest` cron row to the services table: root `/backend`, config `/backend/railway.email-ingest.json`, same variables as the backend)
- Modify: `docs/03-email/overview.md` § Ingest (one bullet on `--scheduled`: no cap, since `last_synced_at` − 1 day or 7 days, one `job_runs` row per run)
- Test: `backend/tests/ingest/email/test_run.py`

**Interfaces:**
- Consumes: `run_job` (Task 1); `upsert_yahoo_mailbox(session) -> Mailbox`, `ingest_fetched(...) -> IngestSummary`, `open_session()` from `ingest.email.pipeline`; `YahooImapAdapter.fetch(*, limit, since) -> FetchResult`.
- Produces:
  - `scheduled_since(last_synced_at: datetime | None, now: datetime) -> date`: `(last_synced_at - timedelta(days=1)).astimezone(UTC).date()`, or `now.astimezone(UTC).date() - timedelta(days=7)` when it's `None`.
  - CLI flag `--scheduled` (store_true). `--limit` default becomes `None` (manual mode treats `None` as 5). `--scheduled` with `--limit` or `--since` → `parser.error("--scheduled sets its own limit and since")`.
  - Scheduled flow in `main`: after the missing-settings check, call `run_job("email_ingest", work)`. `work` does the following: open a session, `upsert_yahoo_mailbox`, compute `since = scheduled_since(mailbox.last_synced_at, datetime.now(UTC))`, commit, `adapter.fetch(limit=0, since=since)`, `ingest_fetched(...)`, close the session, print `summary.render()`, and return `dataclasses.asdict(summary)`. Exceptions propagate, so the process exits non-zero.
  - To make it testable, `main` builds the adapter and session through module-level names (`YahooImapAdapter`, `open_session`, `run_job`) that tests monkeypatch.

- [ ] **Step 1: Write failing tests** in `tests/ingest/email/test_run.py`:
  - `test_since_is_one_day_before_last_sync`: `scheduled_since(datetime(2026,10,8,11,0,tzinfo=UTC), now=datetime(2026,10,8,12,0,tzinfo=UTC)) == date(2026,10,7)`.
  - `test_since_uses_utc_date_near_midnight`: `scheduled_since(datetime(2026,10,8,0,30,tzinfo=UTC), now=…) == date(2026,10,7)`, and a `+02:00` value `2026-10-08T01:30+02:00` (= `2026-10-07T23:30Z`) gives `date(2026,10,6)`.
  - `test_never_synced_fetches_last_seven_days`: `scheduled_since(None, now=datetime(2026,10,8,12,tzinfo=UTC)) == date(2026,10,1)`.
  - `test_scheduled_run_fetches_since_last_sync_with_no_cap`: monkeypatch the settings to valid values, `upsert_yahoo_mailbox` to return a `Mailbox` with `last_synced_at = now - 1h`, `open_session` to a fake, the adapter to a fake recording `fetch` kwargs and returning `FetchResult([], 1, None)`, `ingest_fetched` to return `IngestSummary(fetched=0)`, and `run_job` to a fake that calls `work()` and records `job`. `main(["--scheduled"]) == 0`, fetch got `limit=0` and `since == (last_synced_at - 1 day).date()`, and the job name was `"email_ingest"`.
  - `test_scheduled_run_without_mailbox_fetches_seven_days`: same, with `last_synced_at=None` → `since == today_utc - 7 days`.
  - `test_scheduled_run_records_counts`: with the real `run_job` over a fake job session, the run ends with a row with `status == "ok"` and `counts["new"] == 3` (from `IngestSummary(new=3)`).
  - `test_scheduled_run_failure_is_logged_and_raised`: the fake adapter raises `OSError("imap down")`. `main(["--scheduled"])` raises `OSError`, and the job row has `status == "failed"` and `error == "OSError: imap down"`.
  - `test_scheduled_rejects_limit_and_since`: `pytest.raises(SystemExit)` with code 2 for `["--scheduled", "--limit", "3"]` and `["--scheduled", "--since", "2026-10-01"]`.
  - Keep `test_missing_yahoo_settings_exit` passing unchanged.
- [ ] **Step 2: Run** `uv run pytest tests/ingest/email/test_run.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `scheduled_since`, the flag and the scheduled flow in `run.py`.
- [ ] **Step 4: Create `backend/railway.email-ingest.json`:**

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "deploy": {
    "startCommand": "python -m ingest.email --scheduled",
    "cronSchedule": "*/30 * * * *",
    "restartPolicyType": "NEVER"
  }
}
```

- [ ] **Step 5: Run** `uv run pytest -m "not integration"` and `uv run ruff check .` from `backend/`. Expected: all pass, ruff clean.
- [ ] **Step 6: Commit** `feat(ingest): scheduled email ingest mode and Railway cron config (001/02)`.

## After the tasks (main session)

- Verify the three `(test)` criteria by naming the passing tests.
- Ask the owner for an OK to `alembic upgrade head` (this applies 001/07's `ba98a3ea5b4f` and this task's revision). Then run `uv run alembic check` to confirm the hand-written migration matches the models.
- Ask the owner to create the Railway cron service (settings below). After two runs, check `job_runs` for two `ok` rows and check `email_messages` for duplicates (`group by mailbox_id, message_id having count(*) > 1` → none).

Railway cron service settings (for the owner):
- Source: this repo, **Root directory** `backend`, **Config as Code** path `/backend/railway.email-ingest.json` (Railway doesn't search inside the root directory). That file gives start command `python -m ingest.email --scheduled`, cron `*/30 * * * *` (UTC) and restart policy Never.
- Variables: reference the API service's variables for `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_DIMENSIONS`, `ALLOWED_ORIGINS`, `ENVIRONMENT`, `LANGFUSE_*`. Add the ingest variables `YAHOO_EMAIL`, `YAHOO_APP_PASSWORD`, `EMAIL_AGENT_OWNER_USER_ID`, `TYPESAFE_API_KEY`, plus any of `TYPESAFE_LABEL_MODEL`, `EMAIL_TIMEZONE`, `AI_NEWSLETTER_DOMAINS` that are set locally.

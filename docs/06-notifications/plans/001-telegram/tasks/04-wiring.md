# 001/04 — Wire into email ingest; settings and setup command

## Goal
Every scheduled ingest run detects and sends notifications, and the owner can set the bot up in minutes.

## Scope
- Settings `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `APP_URL` in `config.py` and `.env.example`.
- After extraction and story building in `run_scheduled`: detection, then sending; counts in `job_runs`; a Telegram or detection error never fails the run.
- `python -m ingest.notify --chat-id`: prints chat ids from `getUpdates`.
- `.env` and Railway variables set by the owner.

## Out of scope
- The bank sync cron (no notification events there).

## Acceptance criteria
- Given Telegram failing, when the scheduled ingest runs, then it ends `ok` and `notifications_failed` counts it. (test)
- Given the owner's bot, when they message it and run the setup command, then their chat id is printed. (manual)
- Given the settings in Railway, when the next new invoice or big story is ingested outside quiet hours, then the message arrives within 30 minutes. (manual)

## Dependencies
001/02, 001/03.

## Verified

2026-10-20, branch `feat/telegram-detection`.

- Telegram failing never fails the scheduled run, and the counts land in `job_runs`: `test_scheduled_run_records_then_sends_notifications`, `test_notification_errors_never_fail_the_run`, `test_notification_error_log_has_no_content`. Pass.
- The setup command prints the chat id after the owner messaged the bot (manual): `python -m ingest.notify --chat-id` printed the owner's private chat; `--test` delivered "✅ Folio notifications are set up.", and the owner confirmed it arrived. Pass. (A first run said "No chats yet" until the bot had been messaged, as intended.)
- The next new invoice or big story arrives within 30 minutes once the settings are in Railway (manual): PR #63 merged 2026-10-20 14:37 UTC; the variables were set on `backend` and referenced from `email-ingest`, and both were redeployed. The 15:00 UTC ingest run sent the pending big story at 15:00:41, and the owner received it. Pass.
- Suite: `uv run pytest -m "not integration"`: 665 passed (`test_scheduled_rejects_limit_and_since` deselected). `ruff` is clean.

Review fixes on this branch (fresh reviewer, 2026-10-19): any summary failure falls back; news is keyed by newsletter email and position with a 2-day window, because re-embedding recreates items and most Alpha Signal items have no link; a 429 stops the run; notification errors are logged by type only; the bot token is redacted from httpx's request log. Migrations `d92e6ad10cbb` and `bff323139bdf` are applied (owner OK). The second was first applied empty: the post-write ruff hook had stripped what the edit looked for. It was then filled, dry-run in a rolled-back transaction, and re-applied.

Deferred minors: messages created in the same run go out in random order; any other single 400 stops the run as if misconfigured; a due-soon message held overnight can say "1 day" on the due day; no row locking if two runs overlap; the setup command can show the token in a local error traceback; the migration hard-codes Europe/Berlin.

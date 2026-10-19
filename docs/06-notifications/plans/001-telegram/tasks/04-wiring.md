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

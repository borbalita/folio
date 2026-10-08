# 001/02 — Email ingest runs on a schedule

## Goal
Email ingest runs every 30 minutes on Railway without a manual command, and each run is logged.

## Scope
- A scheduled mode of `python -m ingest.email`: no item cap, fetches from the mailbox's `last_synced_at` minus one day (the last 7 days when it has never run), relying on the existing skip rule for the overlap.
- A job-run log table (job name, start, end, status, counts, error), with RLS; each scheduled run writes one row.
- A Railway cron service for email ingest, `*/30 * * * *`, from the backend code.

## Out of scope
- Bank sync scheduling (001/08).
- Invoice extraction (001/05); once it lands it runs inside every scheduled ingest.

## Acceptance criteria
- Given a mailbox synced an hour ago, when the scheduled mode runs, then it fetches only mail since one day before `last_synced_at`. (test)
- Given a mailbox never synced, when the scheduled mode runs, then it fetches the last 7 days. (test)
- Given a run, when it finishes or fails, then one job-run row records status and counts or the error. (test)
- Given the Railway cron service, when two runs have passed, then two `ok` job-run rows exist and no email is stored twice. (manual)

## Dependencies
None.

## Notes
- Railway skips a run while the previous one is active, so no lock is needed.

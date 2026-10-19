# 001/01 — Notifications table, event detection and launch baseline

## Goal
Each ingest run records one notification row per new invoice, due-soon invoice and big story, exactly once, without sending anything.

## Scope
- `notifications` table with RLS; unique `key`; statuses `pending`, `sent`, `failed`, `skipped`.
- Detection (pure functions over current invoices and stories, plus the keys already recorded): `invoice_new`, `invoice_due` (3 days, Berlin dates, open only), `news_big` (item-level keys); message texts as in the spec; news text left to 001/02 (a placeholder headline-and-links text until then).
- New-and-due-soon invoices get one message; their `invoice_due` row is `skipped`.
- Rows are `skipped` when Telegram settings are missing.
- Migration baseline: `sent` rows for everything existing at migration time.

## Out of scope
- Sending (001/03); summaries (001/02); wiring into ingest (001/04).

## Acceptance criteria
- Given a new open invoice, when detection runs twice, then exactly one `invoice_new` row exists. (test)
- Given a `needs_info` invoice, when detected, then its text says details are missing and shows no amount. (test)
- Given an open invoice due in 3 days by Berlin date, when detected, then an `invoice_due` row is recorded; due in 4 days, none. (test)
- Given an invoice that is new and due in 2 days, when detected, then one message is pending and its `invoice_due` row is `skipped`. (test)
- Given a big story announced earlier and rebuilt under a new id, when detected, then no new row is pending. (test)
- Given Telegram settings missing, when detected, then new rows are `skipped`. (test)
- Given the migration on the dev database, when it runs, then existing invoices and big stories have `sent` rows and the next detection records nothing pending. (manual)

## Dependencies
None.

## Notes
- Implementation plan: [01-detection.plan.md](01-detection.plan.md).

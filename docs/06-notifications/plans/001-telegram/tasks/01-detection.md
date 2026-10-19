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

## Verified

2026-10-19, branch `feat/telegram-detection`.

- A new open invoice is recorded once across two runs: `test_new_open_invoice_once`. Pass.
- `needs_info` says details are missing and shows no amount: `test_needs_info_says_details_missing_and_shows_no_amount`. Pass.
- Due in 3 days is reminded, 4 days is not: `test_due_in_three_days_reminds_four_does_not`, `test_overdue_invoice_gets_no_due_soon_reminder`. Pass.
- New and due in 2 days is one pending message, with `invoice_due` skipped: `test_new_and_due_soon_is_one_message`. Pass.
- A rebuilt or grown big story records nothing pending: `test_big_story_announced_once_by_its_items`, `test_rebuilt_or_grown_story_is_not_announced_again`. Pass.
- Missing Telegram settings skip every new row: `test_disabled_settings_skip_every_new_row`, `test_enabled_needs_all_three_settings`. Pass.
- The migration on the dev database (manual): `d92e6ad10cbb` applied (owner OK). The baseline recorded 10 `invoice_new` and 38 `news_big` rows as `sent`; no open invoice was due within 3 days. RLS is on. A dry run of detection against the database plans nothing. Pass.
- Also: the Berlin date at 23:30 UTC is the next day (`test_record_uses_berlin_date_and_commits`); invoices that arrive already paid are `skipped` (`test_already_paid_invoice_is_skipped`; ruling in the plan file).

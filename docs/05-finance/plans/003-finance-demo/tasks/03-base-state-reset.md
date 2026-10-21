# 003/03 — Base state and reset

## Goal
One call returns the demo user to a fixed, realistic Finance state with dates relative to today.

## Scope
- `app/demo/base_state.py`: about 10 invoices (statuses as in the spec's table) with their emails and PDFs from 003/02, about 40 transactions over 90 days, and the matches behind "matched automatically" and "possible payment found", all as offsets from today. Written as finished rows; no model calls.
- `app/demo/reset.py`: in one transaction, ensure the demo accounts (003/01), delete the demo user's invoices, matches, payment drafts, transactions, emails, attachments, chunks and Finance chat threads, then write the base state.
- `POST /finance/demo/reset` and `python -m app.demo.reset`.

## Out of scope
- The presenter page button (003/06).

## Acceptance criteria
- Given another user's invoices, transactions and threads, when reset runs, then they are unchanged. (test)
- Given a reset, then the counts per status match the spec's table. (test)
- Given a reset on two different days, then due dates and booking dates move with today. (test)
- Given extra demo invoices and payments, when reset runs again, then exactly the base state remains. (test)
- Given an error halfway, then the demo user's data is as before the reset. (test)
- Given a reset, when the demo user opens Finance, then the lists look realistic and every status is visible. (browser)

## Notes
- Implementation plan: [03-base-state-reset.plan.md](03-base-state-reset.plan.md).
- From 003/01's browser check: the invoice routes return 403 for a Finance user without a mailbox. After a reset the demo mailbox exists; also consider returning an empty list instead of 403, and a general 403 message in the frontend.

## Dependencies
003/01, 003/02.

## Verified

2026-10-21, branch `feat/demo-reset` (fast suite: 784 passed; ruff clean). Built inline; one independent whole-branch review. It found that a single flush would insert attachments before their emails (no relationships are mapped), so every real reset would have failed; fixed by flushing one table at a time, and proven by an integration test against the local eval database that fails with the old code.

- Other users' rows unchanged: `test_reset_rebuilds_only_the_demo_users_finance` (integration, local Postgres: the owner's email, invoice, transaction and Finance thread survive two resets) and `test_reset_deletes_only_the_demo_users_rows` (the deletes filter on the demo mailbox, the demo account, and the demo user's Finance threads). Pass.
- Counts per status match the spec's table: `test_base_state_counts_match_the_spec_table`, `test_the_ui_overdue_count_matches_the_spec`. Pass.
- Dates move with today: `test_dates_follow_today` (21 Oct, 31 Jan, 1 Mar, 29 Feb 2028), `test_invoice_numbers_carry_the_invoice_year`. Pass.
- Extra demo invoices and payments → exactly the base state: the integration test adds an invoice, an approved payment, a booking and a chat, then resets: 9 invoices, no drafts, no demo threads. Pass.
- Error halfway → no change: `test_run_reset_keeps_the_old_state_on_error` (no commit; the session closes and rolls back), plus the reset is one transaction in the integration test. Pass.
- Also: the base state never re-matches on the next Book (`test_matching_adds_nothing_to_the_base_state`), two builds share no unique keys, concurrent resets wait on a row lock, no vendor bills twice within two weeks.
- Browser, 2026-10-21, local build against the shared database, signed in as the demo user (owner's OK): `POST /finance/demo/reset` → 9 invoices, 36 transactions. Invoices (Open + Needs info): one overdue, two due soon, one "Possible payment found", the online notice as needs info; Paid: three "Matched automatically" and one "Paid before it arrived". An invoice's PDF opens in the viewer. Transactions show salary, rent, shops and the matched debits over three months; Accounts shows "Demo Bank · Girokonto, valid until 2036". A second reset gave the same 9 invoices (same vendors, statuses and amounts). The 403 noted in 003/01 is gone, since the reset creates the demo mailbox. Pass.
- PR: see the branch's pull request.

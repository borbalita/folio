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

## Dependencies
003/01, 003/02.

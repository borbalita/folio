# 003/05 — Simulated bank booking

## Goal
An approved demo payment can be "booked" into the demo account, and the real matching marks its invoice paid.

## Scope
- `GET /finance/demo/payments`: the demo user's approved payments.
- `POST /finance/demo/payments/{id}/book`: write a booked debit (amount, payee, IBAN, reference, today) into the demo account, then run `match_for_user` for the demo user.

## Out of scope
- The presenter page (003/06).

## Acceptance criteria
- Given an approved payment, when it is booked, then a debit exists and the invoice is paid with an automatic link, and the payment is completed. (test)
- Given a payment that was already booked, when Book is called again, then nothing changes. (test)
- Given another user's payment id, when the demo user books it, then 404. (test)

## Dependencies
003/01.

## Notes
- Implementation plan: [05-bank-booking.plan.md](05-bank-booking.plan.md).

## Verified

2026-10-21, branch `feat/demo-bank-booking`, PR [borbalita/folio#73](https://github.com/borbalita/folio/pull/73).

- Approved payment booked → debit exists, invoice paid with an automatic link, payment completed: `test_booking_an_approved_payment_inserts_once_and_runs_matching` (one debit inserted, committed, matching run for the demo user, statuses read after it) and `test_the_booking_is_a_strong_match_for_its_invoice` (the debit, through the real `propose`, is a `linked` proposal with the IBAN signal, booked today). The automatic link, paid status and completed payment are what `match_for_user` does for a linked proposal (existing matching tests). Pass; the full run on real rows comes with the presenter page (003/06) and rehearsal (003/07).
- Already booked → nothing changes: `test_a_payment_already_booked_and_matched_changes_nothing`, `test_a_second_booking_before_matching_adds_no_debit` (dedup key `demo-booking:<payment id>`). Pass.
- Another user's payment id → 404: `test_another_users_payment_is_not_found`, `test_the_draft_query_is_scoped_to_the_user`. Pass.
- Routes: 404 without `DEMO_USER_ID`, 403 for the owner, the demo user's id passed through (`tests/api/test_demo_booking.py`). The booking INSERT compiles for Postgres.
- Suite: `uv run pytest -m "not integration"`: 733 passed; `ruff check` clean.


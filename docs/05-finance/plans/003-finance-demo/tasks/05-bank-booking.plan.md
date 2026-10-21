# 003/05 — Simulated bank booking: implementation plan

Task: [05-bank-booking.md](05-bank-booking.md). Spec: [README](../README.md), Design → Book payment.

## Code

- `app/demo/booking.py`:
  - `booking_transaction(draft, account_id, today) -> Transaction`: a booked debit of `-draft.amount` in `draft.currency`, counterparty name and IBAN from the draft, remittance = the draft's reference, `bank_code="demo"`, `raw={"demo_booking": <draft id>}`, `dedup_key="demo-booking:<draft id>"`. The dedup key makes a second booking of the same payment impossible (unique per account).
  - `approved_payments(user_id) -> list[dict]`: the user's approved drafts (draft → invoice → email → mailbox of this user), newest approval first: id, invoiceId, payee, amount, currency, reference, approvedAt.
  - `book(user_id, draft_id, today=None) -> dict`: 404 unless the draft belongs to the user; not `approved` → no change; otherwise insert the debit with `ON CONFLICT DO NOTHING` into the demo account (`ensure_demo_accounts`), commit, then `match_for_user(user_id)`. Returns `{"booked": bool, "paymentStatus", "invoiceStatus"}` read after matching.
- `app/api/demo.py`: router `/finance/demo` with `require_demo_user` (404 without `DEMO_USER_ID`, 403 for anyone else): `GET /payments`, `POST /payments/{id}/book`. Registered in `main.py`.
- Today is Europe/Berlin.

## Tests (red first)

- `tests/demo/test_booking.py`:
  - the booking debit strongly matches its invoice: `propose(InvoiceFacts of the invoice, [_debit(booking_transaction(...))])` → one `linked` proposal with `iban` among its signals, booked today;
  - `book` on an approved draft inserts once, commits and runs matching for the user, and reports the statuses after matching;
  - `book` on a completed (already booked) draft inserts nothing and runs no matching; a conflicting insert (booked but not yet matched) reports `booked: false`;
  - `book` on a draft of another user (query finds nothing) → 404.
- `tests/api/test_demo_booking.py`: routes 404 without `DEMO_USER_ID`, 403 for the owner, pass the demo user's id through.

The end-to-end criterion (debit exists, invoice paid with an automatic link, payment completed) rests on the strong-match test above plus the existing matching tests (`apply_proposals` links automatically and marks paid; `complete_for_invoices` completes approved drafts); a real run follows in 003/06's presenter page.

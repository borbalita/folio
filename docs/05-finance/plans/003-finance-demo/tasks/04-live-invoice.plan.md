# 003/04 — Live invoice through the pipeline: implementation plan

Task: [04-live-invoice.md](04-live-invoice.md). Spec: [README](../README.md), Design → New invoice. Written alongside the implementation; it records the approach taken.

- **No split needed:** `ingest_messages(session, mailbox_id, messages, …)` already takes a mailbox; `ingest_fetched` stays the Yahoo wrapper, unchanged.
- `app/demo/live.py`:
  - `resolve_kind(kind, rng)`: `random` picks normal, already paid or online only.
  - `send_invoice(user_id, kind, *, rng, now, open_session, match, **pipeline)`: `draw_invoice` + `invoice_message` (003/02) addressed to the demo mailbox (`demo_address`), `ensure_demo_accounts`, `ingest_messages` inside `propagate_attributes(tags=["demo"])`, then `match_for_user`. Returns `sent` (kind, vendor, number, amount), `invoices` (read after matching, via the now public `serialize_invoice`), `failures` and `error` ("The models could not read this invoice; it is stored as needs info.").
  - Model fakes (`embed`, `classifier`, `invoice_check`, `invoice_extract`) pass through `**pipeline` in tests only.
- `POST /finance/demo/invoices` `{kind}` in `app/api/demo.py`, demo user only; it waits for the models.
- Tests: `tests/demo/test_live_invoice.py` (Normal → open invoice with the built payee, IBAN and amount in the demo mailbox, tag `demo`, matching run; model error → `needs_info` with `extraction_failed`, reported; `random` covers all kinds) and route tests in `tests/api/test_demo_booking.py`.

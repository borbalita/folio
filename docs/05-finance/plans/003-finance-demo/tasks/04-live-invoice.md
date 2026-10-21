# 003/04 — Live invoice through the pipeline

## Goal
The demo user's new invoice goes through the same labelling, check, extraction and matching as a real email.

## Scope
- Split `ingest_fetched` so the part after fetching takes a mailbox; the Yahoo run keeps its behaviour.
- `POST /finance/demo/invoices` with `kind` (normal, already_paid, online_only, random): build the email (003/02), ingest it with the demo mailbox, run `match_for_user` for the demo user, and return the stored invoice and its status.
- Traces carry the tag `demo` and stay content-free.

## Out of scope
- The presenter page (003/06).

## Acceptance criteria
- Given a fake model, when a Normal invoice is sent, then an open invoice with the built payee, IBAN and amount is stored for the demo user. (test)
- Given the Yahoo run, when it ingests, then it behaves as before. (test, existing suite)
- Given the real models, when one invoice of each kind is sent, then Normal is open with correct values, Already paid is paid, and Online only is needs info. (manual: run locally against the real models and note the results)
- Given a model error, then the response says so and the pipeline stores what it stores today. (test)

## Dependencies
003/01, 003/02.

## Notes
- Implementation plan: [04-live-invoice.plan.md](04-live-invoice.plan.md).
- If Jev doesn't label the fictional emails as invoices, the PDF filename rule (`rechnung` in the name) already routes them to detection; check that before changing any wording.

## Verified

2026-10-21, branch `feat/demo-live-invoice`, PR [borbalita/folio#77](https://github.com/borbalita/folio/pull/77).

- Fake model, Normal invoice → open invoice with the built payee, IBAN and amount stored in the demo mailbox: `test_a_normal_invoice_is_stored_open_for_the_demo_user` (also: trace tag `demo`, matching run for the demo user). Pass.
- Yahoo run unchanged: `ingest_fetched` untouched; the existing ingest suite passes. Pass.
- Model error → reported, stored as today: `test_a_model_error_is_reported_and_stored_as_today` (`needs_info`, `extraction_failed`, `failures: 1`, error text). Pass.
- Real models, one invoice of each kind, run locally against the real database: Normal (Malerfachbetrieb Kaya & Brandt, €184.03) stored **open** with the same payee and amount and an IBAN; Already paid (Zahnarztpraxis Dr. Rothenbach, €53.87) stored **paid**; Online only stored **needs info** (`invoice_online`). No model failures. Pass.
- Found on the way: the demo user had no `users` row (only chats created one), so the demo mailbox failed its foreign key. The route now ensures the row first (`test_the_demo_user_sends_a_live_invoice`).
- Suite: `uv run pytest -m "not integration"`: 766 passed after the users-row fix; `ruff check` clean.


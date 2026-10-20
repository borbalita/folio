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
- If Jev doesn't label the fictional emails as invoices, the PDF filename rule (`rechnung` in the name) already routes them to detection; check that before changing any wording.

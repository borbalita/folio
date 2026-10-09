# 001/05 — Payment data extracted from invoice emails

## Goal
Every invoice email yields one or more invoices with payee, IBAN, BIC, amount, currency, invoice number, reference, invoice date and due date, checked and given a status.

## Scope
- An invoices table, several per email, each linked to its email and, when it has one, its PDF; with RLS.
- One structured call per invoice email on the extraction model setting (default `gpt-6.1-sol`), the stored PDFs passed as files, returning a list of invoices.
- Checks: IBAN length and mod-97 checksum, amount above zero, currency EUR. Status `open` when payee, valid IBAN and amount are present, otherwise `needs_info`. A failed call is retried once, then stored as `needs_info` and logged.
- A step in email ingest after labelling, and a backfill command for invoices already stored. Re-extraction never overwrites fields the owner edited.
- Content-free tracing for the call.

## Out of scope
- Showing or editing the fields (001/06).

## Acceptance criteria
- Given mocked model output with two invoices for one email, when extraction runs, then two invoices link to that email and their PDFs. (test)
- Given an IBAN with a wrong checksum, when extraction runs, then the invoice is `needs_info`. (test)
- Given a model failure twice, when extraction runs, then the invoice is `needs_info` and the failure is logged. (test)
- Given an edited invoice, when the backfill reruns, then its fields are unchanged. (test)
- Given real stored invoices, when the backfill runs, then each has fields or `needs_info`. (manual)

## Dependencies
001/04; content-free tracing ([eval plan 004](../../../../02-evaluation/plans/004-content-free-tracing/README.md), tasks 01–03).

## Notes
- Decisions: PDFs go to the model as files; one call on `gpt-6.1-sol`, `gpt-6-astra` next if weak; no trace content.

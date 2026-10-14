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
- Implementation plan: [05-invoice-extraction.plan.md](05-invoice-extraction.plan.md).

## Verified

2026-10-14, branch `feat/invoice-extraction`.

- Two mocked invoices for one email → two invoices linked to the email and their PDFs: `test_two_invoices_link_to_the_email_and_their_pdfs`, plus the ingest path in `test_invoice_email_gets_its_invoices_extracted`. Pass.
- Wrong IBAN checksum → `needs_info`: `test_wrong_iban_checksum_needs_info` and `tests/finance/test_invoice_checks.py`. Pass.
- Two model failures → `needs_info` and logged: `test_two_model_failures_store_needs_info_and_log` (one row with `extraction_failed`, one `invoice_extract_failed` warning, failures counted into `job_runs`). Pass.
- Edited invoice, backfill reruns → fields unchanged: `test_rerun_of_all_keeps_edited_fields` and `test_reextraction_keeps_edited_fields_and_rechecks`; both fail when the edited-field guard is removed. Pass.
- Content-free tracing: `test_extraction_call_is_traced_without_content` (no subject, body, file name, PDF bytes or extracted IBAN in exported spans). Pass.
- Suite: `uv run pytest -m "not integration"` with `EMAIL_RERANK=false` and no Langfuse keys, as CI runs it: 463 passed. `ruff check` clean.
- Real stored invoices, backfill → each has fields or `needs_info`: migration applied, `backfill_invoices` run on 6 invoice emails: 6 invoices, 0 failures, none left without a row. 1 `open` (linked to its PDF), 5 `needs_info` with `no_invoice_found`; 2 of those 5 have a PDF. The owner checked them in the Finance UI on 2026-10-14: the invoices show up, and the two PDFs are correctly not payable invoices. Pass.

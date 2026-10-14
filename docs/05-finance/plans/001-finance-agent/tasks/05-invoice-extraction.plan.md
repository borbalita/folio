# 001/05 — Implementation plan

Task: [05-invoice-extraction.md](05-invoice-extraction.md). Spec: [README](../README.md), Decisions and Design.

**Goal:** every `invoice` email gets one or more `invoices` rows with checked payment fields and a status, during ingest and through a backfill command.

## Data model

`invoices` (`app/database/models/finance/invoice.py`), RLS enabled in its migration, no policies (backend only):

- `email_id` → `emails`, cascade; `attachment_id` → `email_attachments`, set null (ingest re-creates attachments when an email is re-embedded; extraction sets it again).
- `position`: the invoice's place in the model's list; unique with `email_id`. Re-extraction matches rows by position.
- `payee`, `iban`, `bic`, `amount numeric(12,2)`, `currency`, `invoice_number`, `reference`, `invoice_date`, `due_date`, all nullable.
- `status` `open | needs_info` (check constraint; 001/06 adds `paid`), `issues text[]` naming failed checks so 001/06 can say why.
- `edited_fields text[]`: fields the owner changed (001/06 writes it). Re-extraction never sets these.

## Code

1. `app/finance/invoice_checks.py` (pure, reused by 001/06 on save): `normalize_iban`, `iban_valid` (country length table + mod-97), `check(fields) -> (status, issues)`. Issues: `missing_payee`, `missing_iban`, `invalid_iban`, `missing_amount`, `amount_not_positive`, `currency_not_eur`. `open` only with none.
2. `ingest/email/invoices.py`:
   - `ExtractedInvoice` / `InvoiceExtraction` Pydantic output; `source_file` is the 1-based number of the PDF the invoice came from.
   - `extract_with_model(input)`: a PydanticAI `Agent` on `OpenAIResponsesModel(settings.invoice_extraction_model)` (default `gpt-6.1-sol`), structured output. The prompt is subject and body text plus each stored PDF as `BinaryContent(application/pdf)` preceded by a `File N: <name>` text part. Content-free tracing comes from `Agent.instrument_all` (binary content excluded) and the `ingest` tag.
   - `extract_invoices(session, email, attachments, *, extract=None) -> InvoiceOutcome`: call, retry once on `AgentRunError`; then merge into existing rows by position, skipping `edited_fields`, re-checking each row. Two failures: log `invoice_extract_failed` and store one empty `needs_info` row with issue `extraction_failed`, unless rows already exist (they are kept). An empty list stores one `needs_info` row with `no_invoice_found`. Surplus unedited rows are deleted.
3. Pipeline: after attachments, when the label is `invoice`, flush and run the step; `IngestSummary` gains `invoices` and `invoice_failures`, so they land in `job_runs.counts`.
4. Backfill: `uv run python -m ingest.email.backfill_invoices [--all]` — invoice emails without invoices (all with `--all`), one commit per email, recorded as job `invoice_backfill`, traced and tagged `ingest`.
5. Setting `invoice_extraction_model: str = "gpt-6.1-sol"`.

## Tests (red first)

- `tests/finance/test_invoice_checks.py`: valid/invalid IBANs (checksum, length, unknown country), status rules.
- `tests/ingest/email/test_invoices.py`: two mocked invoices → two rows linked to the email and their PDFs; bad checksum → `needs_info`; two failures → one `needs_info` row, warning logged; edited fields survive re-extraction; prompt carries the PDFs as files (FunctionModel).
- `tests/ingest/email/test_backfill_invoices.py`: default picks only emails without invoices; `--all` reruns and keeps edited fields.
- Pipeline: an `invoice` email runs the step and counts invoices; other labels don't.
- Migration lists `invoices` in `RLS_TABLES` (existing RLS test).

## Manual

Run the migration and the backfill against the real database; each stored invoice email has fields or `needs_info`.

# 001/06 — Implementation plan

Task: [06-invoice-dashboard.md](06-invoice-dashboard.md). Spec: [README](../README.md).

**Goal:** the Finance invoices list shows extracted invoices (one row per invoice), filterable, overdue first; the invoice page shows each invoice's fields beside its PDF, editable and re-checked on save; invoices can be marked paid and un-marked, one or several.

## Data model

- `InvoiceStatus.PAID`; the check constraint is replaced by hand (autogenerate misses check changes).
- `paid_at timestamptz`, `paid_by varchar(16)` (`owner` now; 001/09 adds `match`), both null unless paid.

## Backend

1. `app/finance/invoice_checks.py`: `recheck(row)` sets `issues` and, unless the row is paid, `status`. Ingest's re-extraction uses it too, so a re-extracted paid invoice stays paid.
2. `app/finance/invoice_edits.py` (pure, on ORM rows):
   - `apply_edit(row, changes)`: blank → null, IBAN normalized, BIC and currency upper-cased; changed names added to `edited_fields`; `recheck`.
   - `set_paid(row, paid, now)`: paid → status `paid`, `paid_at`, `paid_by="owner"`; un-paid → clears both and `recheck` gives `open` or `needs_info`.
3. `app/database/invoices.py`:
   - `list_invoices(mailbox_ids)` now returns invoice rows joined with their email (`emailId`, subject, from, sentAt, fields, status, issues, paidBy).
   - `get_invoice(email_id, …)` adds the email's `invoices` (with `attachmentId`).
   - `update_invoice(invoice_id, changes, mailbox_ids)` and `set_invoices_paid(ids, paid, mailbox_ids)`: scoped through the email's mailbox; 404 unknown, 403 foreign; all-or-nothing for several.
4. Routes (owner-only router): `PATCH /finance/invoices/items/{invoice_id}` (Pydantic body, every field optional, amount as decimal string or number, dates ISO) and `POST /finance/invoices/items/paid` `{ids, paid}`.

## Frontend

- `api.ts`: `Invoice` type, `listInvoices` → invoices, `updateInvoice`, `setInvoicesPaid`.
- `InvoicesPage`: filters (status checkboxes defaulting to open and needs_info, from/to date on invoice date or else sent date, payee text) applied client-side; sort overdue first (oldest due first), then newest; checkboxes with Mark paid / Mark unpaid for the selection.
- `InvoiceList`: table-like rows: select, payee, invoice number, amount, due date (overdue highlighted), status; row links to the email page.
- `InvoicePage`: per invoice a two-column block, `InvoiceFields` form left (native form, Save, status and reasons, Mark paid / Mark unpaid) and its PDF right; PDFs not linked to an invoice and the message below.

## Tests (red first)

- `tests/finance/test_invoice_edits.py`: needs_info + valid IBAN and amount → open, fields in `edited_fields`; blank clears; mark paid on two → paid by owner; un-mark → open / needs_info by their fields; edit of a paid invoice keeps it paid.
- `tests/ingest/email/test_invoices.py`: re-extraction keeps a paid invoice paid.
- `tests/api/test_finance_invoices.py`: PATCH and paid routes forbidden for another user; owner calls pass mailbox scope; body validation (422 on bad date).
- `tests/database/test_invoices.py`: update/paid reject foreign mailboxes and unknown ids (MagicMock session).

## Browser

Run backend and https dev server; check the list default filter and order, and the page's side-by-side layout.

# 001/06 — Invoice dashboard with extracted fields

## Goal
The owner sees, filters, corrects and marks invoices from the Finance invoices list and page.

## Scope
- List columns: payee, invoice number, amount, due date, status. Filters: status (default open and needs_info), date range, payee text; overdue first.
- Invoice page: PDF beside the extracted fields; fields editable, re-checked on save.
- Mark paid and un-mark, one or several, recording that the owner did it.

## Out of scope
- Matches (001/09) and payments (001/10).

## Acceptance criteria
- Given open, needs_info and paid invoices, when the list opens, then only open and needs_info show, overdue first. (browser)
- Given a needs_info invoice, when the owner enters a valid IBAN and amount, then it becomes open. (test)
- Given two selected invoices, when Mark paid is used, then both are paid by the owner; un-marking returns each to open or needs_info. (test)
- Given an invoice, when its page opens, then the PDF and the fields show side by side. (browser)

## Dependencies
001/05.

## Notes
- Implementation plan: [06-invoice-dashboard.plan.md](06-invoice-dashboard.plan.md).

## Verified

2026-10-15, branch `feat/invoice-dashboard`.

- Open, needs_info and paid invoices → list shows only open and needs_info, overdue first: browser, this branch run locally against the real database (6 invoices). Default filter showed 1 Open and 5 Needs info; the overdue Open invoice (due Oct 7) came first, marked overdue. The status filter and ordering logic is in `InvoicesPage.tsx`. Pass.
- needs_info invoice + valid IBAN and amount → open: `test_valid_iban_and_amount_make_a_needs_info_invoice_open`, and through the database layer `test_update_rechecks_and_commits`. Pass.
- Two selected invoices → Mark paid → both paid by the owner; un-marking returns each to open or needs_info: `test_mark_paid_on_two_records_the_owner`, `test_unmark_returns_each_to_open_or_needs_info`, `test_two_invoices_are_marked_paid_and_back`; all-or-nothing on a foreign or unknown id. Pass.
- Invoice page → PDF and fields side by side: browser, on the Open invoice: fields beside the PDF at 1440px; below 1024px the PDF stacks under the fields. Pass.
- Also: a paid invoice stays paid through edits and re-extraction (`test_editing_a_paid_invoice_keeps_it_paid`, `test_reextraction_keeps_a_paid_invoice_paid`).
- Suite: `uv run pytest -m "not integration"` (no Langfuse keys, `EMAIL_RERANK=false`): 508 passed; `ruff check` clean; `pnpm tsc --noEmit` and `pnpm lint` clean.
- Migration `0cb48528ec95` (after 001/08's `2e8ef7b9c0f9`) applied to the database.


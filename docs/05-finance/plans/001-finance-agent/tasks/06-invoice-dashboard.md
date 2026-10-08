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

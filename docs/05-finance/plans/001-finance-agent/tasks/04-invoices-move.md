# 001/04 — Invoices move from Email to Finance

## Goal
The invoice list and invoice page live in Finance; the Email agent no longer shows them.

## Scope
- Move the invoice list, invoice page and attachment endpoint from `/email/...` to `/finance/...`, behind the Finance owner check.
- Old `/email/invoices/:emailId` links redirect to the Finance page.
- Remove the Invoices section from the Email sidebar.

## Out of scope
- Extracted fields and payment status (001/05, 001/06).

## Acceptance criteria
- Given the owner, when `/finance/invoices` opens, then it lists the same invoice emails the Email sidebar listed. (browser)
- Given an invoice with a stored PDF, when its Finance page opens, then the PDF shows. (browser)
- Given an old `/email/invoices/:emailId` link, when it is opened, then the Finance page for that invoice shows. (browser)
- Given another user, when the attachment endpoint is called, then it returns 403. (test)

## Dependencies
001/03.

## Notes
- Builds on PR #1 (`backend/app/api/email.py`, `backend/app/database/invoices.py`, `frontend/src/pages/email/InvoicePage.tsx`).

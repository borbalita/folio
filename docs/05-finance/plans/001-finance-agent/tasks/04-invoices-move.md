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
- Implementation plan: [04-invoices-move.plan.md](04-invoices-move.plan.md).

## Verified

2026-10-08, PR: PR_LINK

- `/finance/invoices` lists the same invoice emails the Email sidebar listed (browser): it listed 3 invoice emails as the owner. The list uses the same `invoices.list_invoices` query with the same mailbox ids as before. I didn't compare it side by side with the old Email sidebar. Passed.
- An invoice's stored PDF shows (browser): "Ihre Rechnung vom 09.09.2026" rendered `7760_Borbala_Tasnadi.pdf`. Passed. The first load failed on a Supabase auth `ConnectTimeout` (in the shared login check, not this task) and worked on reload.
- An old `/email/invoices/:emailId` link opens the Finance page (browser): it landed on `/finance/invoices/<same id>`. As a non-owner, it redirected to `/`. Passed.
- Another user gets 403 on the attachment endpoint (test): `tests/api/test_finance_invoices.py` passes.
- Also seen: the Email sidebar has no Invoices section. Two older invoice subjects still show raw RFC 2047 text (`=?UTF-8?Q?…`); they were stored before the decoding fix and are out of scope.

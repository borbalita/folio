# 001/04 — Implementation plan

Written after implementation; it records the approach taken.

## Backend

1. Move `GET /invoices`, `GET /invoices/{email_id}` and `GET /attachments/{attachment_id}` from `app/api/email.py` to `app/api/finance.py`. Delete `email.py` and its router registration.
2. Each route runs the router-level Finance owner check first, then resolves the owner's mailbox ids with `require_email_access`, and passes them unchanged to `app/database/invoices.py`.
3. Remove the 001/03 placeholder `GET /finance/access`.

## Frontend

1. Move the invoice list and invoice page to `components/finance/` and `pages/finance/`, and fill the Invoices page.
2. Redirect `/email/invoices/:emailId` to `/finance/invoices/:emailId`. The redirect sits outside the Email guard, so the Finance guard decides.
3. Remove the Invoices section and its fetch from the Email sidebar.

## Tests

- Move the invoice route tests to `tests/api/test_finance_invoices.py`.
- The owner gets the list, detail and PDF, scoped to their mailboxes.
- Another user with a mailbox gets 403 on all three routes, so only the owner check can cause it.
- A user with no mailbox gets 403.

## Docs

- Update `docs/03-email/` where it still describes invoices as Email features.

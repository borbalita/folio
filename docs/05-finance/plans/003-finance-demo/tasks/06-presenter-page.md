# 003/06 — Presenter page and list refresh

## Goal
The owner runs the demo from a phone or a second tab, and the app the audience sees updates on its own.

## Scope
- `/finance/demo` in the frontend, phone-sized, only for the demo user, not in the sidebar: New invoice (kind, Send, log of recent sends with status), Payments to book (Book), Reset demo (with confirmation).
- Invoice list, invoice page, payments and transactions refetch every 5 s while the tab is visible and on window focus, for every user.

## Out of scope
- A visible demo guide for self-serve.

## Acceptance criteria
- Given the demo user on a phone-sized screen, when they open `/finance/demo`, then the three blocks fit without horizontal scrolling. (browser)
- Given the owner, when they open `/finance/demo`, then they don't see the controls. (browser)
- Given the app open in one tab, when an invoice is sent from the presenter page, then it appears in the list within 30 s without a reload. (browser)
- Given the full run, reset, send, Pay, Approve with QR, Book, then the invoice shows as paid and matched automatically. (browser)

## Dependencies
003/03, 003/04, 003/05.

## Notes
- Added at the owner's request (2026-10-21): an open invoice with a payment approved in the last 5 days shows as **Pending** (display only; the invoice stays open in the database), so the demo reads open → pending → paid. After 5 days without a debit it shows open again.
- Implementation plan: [06-presenter-page.plan.md](06-presenter-page.plan.md).

## Verified

2026-10-21, branch `feat/demo-presenter`, PR [borbalita/folio#79](https://github.com/borbalita/folio/pull/79), local backend and frontend against the real database, signed in as the demo user.

- Demo user, phone size → the three blocks fit without horizontal scrolling: at 375 × 812 the page width equals the screen width (375). Pass.
- Owner → no controls: not run in the browser (the session stayed signed in as the demo user); the owner accepted it as covered on 2026-10-21. The server returns 403 to the owner on every demo route (`test_the_owner_cannot_book_demo_payments`, `test_the_owner_cannot_send_live_invoices`), and the page shows no controls on 403 or 404 ("This page is only for the demo account."). Pass by test.
- Invoice sent from the presenter page with the list open in another, visible tab → the list went from 2 to 5 rows within 30 s, without a reload. Pass.
- Full run: Reset → base state ("The demo is back to its base state", list as in the spec); Pay → Approve with QR → the invoice shows **Pending** → Book on the presenter page ("invoice paid") → the invoice page shows Paid and "Matched automatically · Demo Bank · same amount, IBAN, invoice number in the transfer text, payee name"; a second Reset returns it to Open. Pass.
- Pending: `tests/finance/test_payment_pending.py` (only a recent approved payment counts; 5 days). Suite: 798 passed; `ruff check`, `pnpm tsc --noEmit`, `pnpm lint` clean.


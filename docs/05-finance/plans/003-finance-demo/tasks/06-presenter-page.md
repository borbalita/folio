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
- Implementation plan: [06-presenter-page.plan.md](06-presenter-page.plan.md).

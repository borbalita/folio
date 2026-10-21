# 003/06 — Presenter page and list refresh: implementation plan

Task: [06-presenter-page.md](06-presenter-page.md). Spec: [README](../README.md), Design → Presenter page, Refresh. Written alongside the implementation; it records the approach taken.

- **Refresh:** `useRefresh(refresh)` (`frontend/src/lib/useRefresh.ts`) calls a page's quiet refetch every 5 s while `document.visibilityState` is visible, on becoming visible, and on window focus. Wired into the invoice list, invoice page, payments page and transactions; a failed refresh keeps what is on screen. The payments page keeps its current card.
- **Presenter page:** `/finance/demo`, inside the Finance access guard but outside `FinanceLayout`, so no sidebar and phone width (`max-w-md`). It first loads `GET /finance/demo/payments`; 403 or 404 shows "This page is only for the demo account." and no controls, so the server alone decides who the demo user is.
  - **New invoice:** Normal, Already paid, Online only, Random; Send (90 s timeout, the models take 10–20 s); a log of the last 5 sends with vendor, amount and the stored status or the error.
  - **Payments to book:** the approved demo payments, refreshed every 5 s; Book shows the result.
  - **Reset demo:** two-step confirmation, then `POST /finance/demo/reset` (003/03); the payments block remounts afterwards.
- No backend change.

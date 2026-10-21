# 001/13 — Finance overview and end-to-end check

## Goal
`docs/05-finance/overview.md` describes what was built, and the success criteria are checked once end to end.

## Scope
- Overview: invoices and extraction, bank sync and its limits, matching, QR payments, schedules, expiry handling, owner-only access and tracing, what plan 002 adds. Linked from `docs/README.md`.
- The owner's hand test of real invoices and the other success criteria.
- Checks moved here from 001/09 and 001/10: undoing an automatic match in the browser, the 90-day spot check of matches, and a QR-paid invoice turning paid after the next bank sync.

## Out of scope
- New behaviour.

## Acceptance criteria
- Given the merged plan, when `docs/README.md` is opened, then it links the overview, which links back to this plan. (browser)
- Given real invoices from the last months, when the owner compares each with Finance, then payee, IBAN, amount and reference are correct or the invoice is `needs_info`. (manual)
- Given the success criteria in the spec, when each is checked, then all pass or the failures are recorded. (manual)

## Dependencies
All other tasks.

## Verified

2026-10-21, branch `docs/finance-overview`.

- `docs/README.md` links the overview, and the overview links back to this plan (browser): on GitHub (branch `docs/finance-overview`), `docs/README.md` has an Overview link to `05-finance/overview.md`, which renders and whose "plan 001" link points to `plans/001-finance-agent/README.md`. Pass.
- The owner's hand test of real invoices (manual): **skipped** at the owner's request (2026-10-21).
- The success criteria (manual):
  1. A real invoice email appears in Finance within 30 minutes: **pass.** The two newest invoice emails (2026-10-19) were in Finance 30 and 6 minutes after arriving, both as `needs_info` with the reason recorded. Older invoices were backfilled before extraction was scheduled.
  2. A QR-paid invoice turns paid after the next bank sync: **not shown.** The Praxis invoice (€45.00) has an approved payment from 2026-10-16, but no €45.00 debit is in N26, ING or PayPal through 2026-10-20 (all synced; last sync `ok` 2026-10-21 04:02 UTC), so it is still open: the owner decided not to pay that bill yet (2026-10-21). No matching failure. The owner will test with a different bill, ideally paid from a chat payment card, which also shows criterion 5.
  3. A 90-day spot check shows every invoice matched, suggested or genuinely open: **pass, with a gap.** 10 invoices: 4 `needs_info`, 4 paid before they arrived, 1 marked paid by the owner, 1 open (Praxis), which has no equal-amount debit, so it is genuinely open. No automatic match has happened on real data yet.
  4. Expiry emails and Reconnect all: **skipped** at the owner's request (as in 001/11).
  5. In chat, "what do I still need to pay?" and "pay them all" show cards, and nothing can be approved by the assistant: **partly shown** (001/12, 2026-10-16). The question showed an invoice card. "Pay them all" correctly prepared nothing, because the only open invoice already had an approved payment, so no payment card appeared. The assistant has no approving tool (`test_no_tool_can_approve`).
  6. Nobody but the owner can reach a Finance route: **pass.** On the live API, `/finance/invoices`, `/transactions`, `/bank-connections` and `/payment-drafts` answer 401 without a sign-in and with a bogus token. A signed-in non-owner gets 403 (`test_finance_routes_are_forbidden_for_another_user`, `test_former_owner_cannot_use_an_existing_finance_thread`).
  7. The owner's hand test finds the extracted values correct: **skipped** at the owner's request.
- Checks moved here from 001/09 and 001/10:
  - Undoing an automatic match in the browser: **not possible yet.** No automatic match exists on real data.
  - The 90-day spot check: see criterion 3.
  - A QR-paid invoice turning paid: see criterion 2.

The plan stays In progress: criteria 2 and 5 are not fully shown, and 4 and 7 were skipped.

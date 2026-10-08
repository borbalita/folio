# 001/13 — Finance overview and end-to-end check

## Goal
`docs/05-finance/overview.md` describes what was built, and the success criteria are checked once end to end.

## Scope
- Overview: invoices and extraction, bank sync and its limits, matching, QR payments, schedules, expiry handling, owner-only access and tracing, what plan 002 adds. Linked from `docs/README.md`.
- The owner's hand test of real invoices and the other success criteria.

## Out of scope
- New behaviour.

## Acceptance criteria
- Given the merged plan, when `docs/README.md` is opened, then it links the overview, which links back to this plan. (browser)
- Given real invoices from the last months, when the owner compares each with Finance, then payee, IBAN, amount and reference are correct or the invoice is `needs_info`. (manual)
- Given the success criteria in the spec, when each is checked, then all pass or the failures are recorded. (manual)

## Dependencies
All other tasks.

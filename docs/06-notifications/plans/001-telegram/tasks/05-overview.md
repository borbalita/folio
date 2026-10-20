# 001/05 — Overview and end-to-end check

## Goal
`docs/06-notifications/overview.md` describes what was built, and the success criteria are checked once.

## Scope
- Overview: events, message texts, quiet hours, retries, settings and bot setup, privacy. Linked from `docs/README.md`.
- The success criteria, checked against real messages.

## Out of scope
- New behaviour.

## Acceptance criteria
- Given the merged plan, when `docs/README.md` is opened, then it links the overview, which links back to this plan. (browser)
- Given the success criteria, when each is checked, then all pass or the failures are recorded. (manual)

## Dependencies
All other tasks.

## Verified

2026-10-20, branch `docs/notifications-overview`.

- `docs/README.md` links the overview, and the overview links back to this plan (browser): **pending**, checked on GitHub after push.
- The success criteria (manual):
  1. A real invoice email reaches Telegram within 30 minutes: **pending**, waiting for the next invoice email.
  2. An open invoice due in 3 days is reminded once: **pending**, waiting for an invoice 3 days before its due date.
  3. A big AI story reaches Telegram once with a summary and links: **pass.** The 15:00 UTC run (2026-10-20) sent "OpenAI Reports Gains in Modernizing Legacy Code" with a 2-sentence summary and the TLDR link; the owner received it. Its second item (Alpha Signal) is `skipped`. The 15:32 run recorded and sent nothing new.
  4. Nothing is sent between 22:00 and 07:00 Berlin: **pending**, waiting for an event in quiet hours (covered by `test_quiet_hours`).
  5. Ingest succeeds and failures are visible: **pass.** Both runs are `ok`, with `notifications_new/sent/failed/held` in `job_runs.counts` (2/1/0/0, then 0/0/0/0); no row failed. The failure paths are covered by tests, not by breaking production.
  6. Turning notifications on sends nothing old: **pass.** All 48 launch rows (10 invoices, 38 news items) are still `sent` with empty text; the only message since launch is the new story; nothing was recorded as `skipped` between the merge and the redeploy.

Found: the message carried only the TLDR link. 282 of 287 Alpha Signal items have no link, because ingest keeps a newsletter's text and drops the link targets behind its buttons (TLDR prints its links as text). The fix belongs to email ingest; it is not part of this plan.

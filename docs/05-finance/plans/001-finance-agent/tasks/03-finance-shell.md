# 001/03 — Finance agent shell, owner only

## Goal
The owner sees a Finance card and an empty Finance area; nobody else can reach anything in it.

## Scope
- Setting `finance_owner_user_id`; Finance is off for everyone when it is unset.
- `GET /me` lists `finance` only for the owner; the picker shows the Finance card only then.
- `chat_threads.agent` accepts `finance`; Finance threads and a stub agent reply, like the email agent's first slice.
- `/finance` route with the sidebar (Invoices, Transactions, Accounts links, empty pages) and redirect to `/` for anyone else.
- A shared owner check used by every later Finance route.

## Out of scope
- Any invoice, bank, or chat behaviour beyond the stub.

## Acceptance criteria
- Given the owner, when `/me` is called, then `agents` contains `finance`. (test)
- Given another user, when any `/finance` API route is called, then it returns 403. (test)
- Given `finance_owner_user_id` unset, when the API starts, then it starts and `/me` lists no `finance` for anyone. (test)
- Given the owner in the browser, when `/` loads, then the Finance card is shown and opens `/finance`; given another user, then there is no card and `/finance` redirects to `/`. (browser)

## Dependencies
None.

## Notes
- Decision: Finance is its own agent; the owner is a fixed setting, failing closed.
- Implementation plan: [03-finance-shell.plan.md](03-finance-shell.plan.md).

## Verified

2026-10-08, PR: [#14](https://github.com/borbalita/folio/pull/14)

- Owner `/me` lists `finance` (test): `tests/api/test_finance_access.py` passes.
- Another user gets 403 on `/finance` API routes (test): `test_finance_access.py` and `test_finance_invoices.py` pass. The thread messages, delete and stream routes also return 403 on a Finance thread.
- Setting unset → API starts and nobody gets `finance` (test): `test_finance_access.py` passes; the whole suite runs with the setting unset (191 passed).
- Owner sees the Finance card and it opens `/finance`; another user gets no card and `/finance` redirects to `/` (browser): checked as `tasnadibori@yahoo.com`. The card opened `/finance/invoices` with Invoices, Transactions, Accounts and Sign out. Then the backend was restarted with an owner id matching nobody: no card, and `/finance/invoices` redirected to `/`. Passed.

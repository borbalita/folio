# 001/03 — Implementation plan

Written after implementation; it records the approach taken.

## Backend

1. Setting `finance_owner_user_id` in `app/config.py`: an optional UUID, blank → `None`, sharing the validator with `email_agent_owner_user_id`. Document it in `.env.example`.
2. `app/auth/finance_access.py`: `is_finance_owner(user)` is false when the setting is unset. `require_finance_owner(user)` raises 403 otherwise.
3. `agents_for` lists `finance` only when `is_finance_owner` is true.
4. `app/api/finance.py`: a router with prefix `/finance` and a router-level owner dependency, so later routes can't skip the check.
5. `chat_threads.agent` accepts `finance`: the model check constraint plus a migration (drop and re-create `ck_chat_threads_agent`).
6. Thread and stream routes check access per agent: `require_agent_access(user, agent)`, used on create, list, delete, messages and stream.
7. Stub reply for Finance threads through the existing canned-text stream, like the email agent's first slice. It saves no history.

## Frontend

1. `lib/agents.ts`: a Finance entry with `hasThreads: false`, so the picker opens `/finance` instead of creating a thread.
2. `/finance` under `AgentRoute agent="finance"` (redirects to `/` without `finance` in `/me`). `FinanceLayout` has a sidebar with Invoices, Transactions and Accounts; each page is empty.

## Tests

- Owner gets `finance` in `/me`; others and an unset setting don't.
- Another user gets 403 on `/finance/*`, on thread create and list for `finance`, and on messages, delete and stream for an existing Finance thread.

# 001 — Test database for agent runs

- Created: 2026-11-05
- Status: In progress
- Current stage: test project set up and sign-in works; removing other prod values from local `.env` is left

## Problem

Unattended runs couldn't do `(browser)` checks or run migrations, because the only database held real data. Those checks need Supabase Auth, migrations and RLS somewhere safe.

## Decisions

- **A second Supabase project** (`eu-central-1`), not plain Postgres: login uses Supabase Auth, and chat threads use the Data API.
- **Local `.env` points at the test project;** prod values live in Railway. Rejected: a separate `.env.test`, because a wrong line could still run a migration or reset against prod.
- **Demo data comes from the demo reset,** not a copy from prod.
- **The test login is a public fixture,** [frontend/e2e/test-user.json](../../../../frontend/e2e/test-user.json) (owner's choice, 2026-11-06). Agents can't read `.env`, and shouldn't, because it holds other real credentials. The login is useless without the project's URL and reaches only invented data. Rejected: a permission rule letting agents read `.env`.

## Done

- 2026-11-06: migrations at head, demo user created, demo reset seeded 9 invoices, 40 transactions, 29 stories and 40 mails. An agent read the fixture and signed in; the picker and `/news` loaded with no console errors, and a thread opened.

## Left

- Clear the prod values still in local `backend/.env` and remove leftover `.env` copies. Prod migrations then run with `railway run --service backend uv run alembic upgrade head`.
- Add test-project checks to `/overnight`'s pre-flight.
- Not checked yet: a full chat turn on the test project.

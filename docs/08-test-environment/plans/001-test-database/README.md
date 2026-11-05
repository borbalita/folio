# 001 — Test database for agent runs

- Created: 2026-11-05
- Status: Draft
- Current stage: idea saved; not specified yet

## Problem

Unattended runs can't do `(browser)` checks or run migrations, because the only known database holds real data. Those checks need Supabase Auth, migrations and RLS somewhere safe.

## Idea

A second, free Supabase project with its keys in a separate env file. The owner creates the project and the secrets. Migrations run against it, and the demo reset can probably seed its invented newsletters as test data (not confirmed). `/overnight`'s pre-flight then checks that it exists. Checks that need real newsletters stay manual.

Rejected: making this a task in AI News plan 002, because an unattended run can't create the project and it serves every later plan. `docker-compose.eval.yml`: a local database for evals, with no Auth.

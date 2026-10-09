# Docs

Folders are numbered by when they were started. A folder keeps growing after that; the number does not change. The next folder takes `06-`.

## Platform

One app, several agents. Sign-in lands on a picker. Each agent has its own chat threads. Shared setup is in `00-guides/`. Product behavior lives in the numbered folders below.

## 00-guides

Setup that every agent uses.

- [Supabase](00-guides/supabase-setup.md)
- [Backend](00-guides/backend-setup.md)
- [Frontend](00-guides/frontend-setup.md)

## 01-document-copilot

The filing assistant.

- [Architecture](01-document-copilot/architecture.md)
- [Client brief](01-document-copilot/client-brief.md)

## 02-evaluation

How the copilot is traced and evaluated. Later agents add their checks here.

- [Evals and monitoring](02-evaluation/evals-todo.md)

## 03-email

The mailbox agent: Yahoo ingest, labels, newsletter stories, and chat over that mail.

- [Spec](03-email/spec.md)
- `03-email/todo.md` is the build guide. It is gitignored.
- [Overview](03-email/overview.md)

## 04-memory

Shared by both agents: thread history sent to the model, and long-term memories the user can see and delete.

- [Spec](04-memory/spec.md)
- `04-memory/overview.md` is written when that build is done.

## 05-finance

The finance agent: invoices from mail, bank and PayPal transactions, categories, and payments you approve.

- [Plans](05-finance/plans/README.md)

## Legal

Linked from the Enable Banking application.

- [Privacy](legal/privacy.md)
- [Terms](legal/terms.md)

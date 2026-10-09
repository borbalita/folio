# 001 — Finance agent: invoices, bank sync, and payments

- Created: 2026-10-06
- Status: In progress
- Current stage: Implementation; 001/03, 001/04 and 001/07 done

## Approval state

- 2026-10-06: Stage 1 confirmed (problem, goals, non-goals). Settled in chat: Finance is its own agent; bank data comes from live APIs; invoices are paid by SEPA transfer to an IBAN; every payment is confirmed in the bank app. PayPal linking, transfers, categorization and spending go to plan 002.
- 2026-10-07: invoices move from the Email agent to Finance.
- 2026-10-08: Stage 2 complete; the data-check consent sessions closed. Changed at the owner's request: syncing PayPal moves into this plan.
- 2026-10-08: Stage 3 decisions approved. Stage 4 design, success criteria and risks approved; expiry emails and Reconnect all added at the owner's request.
- 2026-10-08: Stage 5 task breakdown approved; the plan is Ready.

## Problem

Invoices arrive by email and get the `invoice` label, but nothing tracks whether they are paid. Checking means opening each PDF and searching two banking apps (N26, ING), and paying means copying IBAN, amount and reference by hand. The owner wants one place that shows which invoices are open, marks them paid when the money has left, and prepares payments for the rest, from a dashboard or from chat.

## Current system

- **Invoices:** email ingest labels a message `invoice` with one Jev decision ([labels.py](../../../../backend/ingest/email/labels.py)) and stores every PDF as bytea ([pipeline.py](../../../../backend/ingest/email/pipeline.py)). Nothing is extracted. The Email agent lists invoices in its sidebar and shows an invoice page with the stored PDFs, behind an owner-only attachment endpoint ([email.py](../../../../backend/app/api/email.py), [invoices.py](../../../../backend/app/database/invoices.py), [InvoicePage.tsx](../../../../frontend/src/pages/email/InvoicePage.tsx)).
- **Extraction pattern:** newsletter extraction ([news.py](../../../../backend/ingest/email/news.py)) is a structured LLM call with its own model and effort settings in [config.py](../../../../backend/app/config.py); eval plan 003 benchmarked the models.
- **Agents:** `chat_threads.agent` is checked to `documents`, `email` ([thread.py](../../../../backend/app/database/models/chat/thread.py)); the picker reads [agents.ts](../../../../frontend/src/lib/agents.ts). Every table has RLS.
- **Tracing:** all agents send full content to Langfuse today ([observability.py](../../../../backend/app/observability.py)); [eval plan 004](../../../02-evaluation/plans/004-content-free-tracing/README.md) makes it content-free.
- **Scheduling:** none; email ingest is a manual CLI and Railway runs only the API. No bank integration.
- **Memory:** [04-memory](../../../04-memory/spec.md) (draft) plans thread history for the existing agents; Finance would need the same.

## Goals and non-goals

Goals:

- Every invoice email has its payment data extracted, checked, and editable.
- Transactions from the N26 main account, ING and PayPal arrive on a schedule.
- An invoice turns paid when a matching debit appears, or when the owner marks it.
- The owner selects open invoices, picks an account, checks each payment beside its invoice, and pays it by QR in the bank app.
- The Finance chat answers "what do I still need to pay?" and prepares payments, but cannot approve them.
- Email ingest runs on a schedule.

Non-goals: paying through a bank API; partial or combined payments; non-EUR invoices; budgets and multiple users; PayPal ↔ bank linking, transfers between own accounts, N26 Spaces, categorization and spending (plan 002).

## Key concepts

- **PSD2 account access.** EU banks give licensed providers API access with the customer's consent. Enable Banking holds the licence; this app is its client and never sees bank logins.
- **Consent session.** The owner approves on the bank's page and returns with a code that becomes a session, valid at most 180 days for N26, ING and PayPal. Renewal always needs the owner at the bank.
- **Restricted mode.** Enable Banking is free while the app reads only accounts linked in its control panel. The app has only the `AIS` service (reading).
- **Request signing.** Every API call carries an RS256 JWT signed with the app's private key.
- **Unattended access limit.** About four reads per account per day without the owner present; syncs the owner starts don't count.
- **Transactions.** Amount and direction, booking date, status (booked or pending), counterparty, remittance text. Bank ids are optional and not always unique.
- **EPC QR code (GiroCode).** A standard QR code holding a SEPA transfer; the N26 and ING apps scan it and pre-fill a transfer for the owner to confirm.

Sources and the real-data and payment tests: [research.md](research.md).

## Decisions

- **Invoices live in Finance.** Rejected: keeping them in Email, which splits one invoice over two agents.
- **This plan syncs the N26 main account, ING and PayPal through Enable Banking**, not N26 Spaces (no IBAN, no payments of their own). Reversible: Spaces are already in the N26 consent.
- **Payments leave through a GiroCode QR.** Approve unlocks only after the owner ticks that payee, IBAN, amount and reference match the invoice shown beside it; copy buttons are the fallback. Rejected for now: payment initiation, which the app cannot use (`403 ACCESS_DENIED`, only `AIS` enabled). Reversible if Enable Banking enables `PIS`.
- **A strong match marks an invoice paid automatically:** equal amount and equal IBAN or reference. Equal amount and a similar name is a suggestion. Automatic links are labelled and undone in one click. Rejected: confirming every match, since real transfers always carry IBAN and reference.
- **Invoice PDFs go to the model as files,** so scans work and no PDF library is added. Rejected: local text extraction.
- **One extraction call on `gpt-6.1-sol`,** its own setting, `gpt-6-astra` next if weak. Guarded by the IBAN checksum, plausibility checks, the owner's tick and the bank's payee-name check; the owner tests by hand once built. Rejected for now: a second extraction compared field by field, added if hand testing finds wrong amounts.
- **Email ingest every 30 minutes; bank sync three times a day,** as Railway cron (UTC), plus Sync now.
- **The Finance chat answers with cards** that reuse the dashboard's invoice and payment components and show current state; tools prepare but never approve. Rejected: text-only answers.

## Design

```text
Email ingest (cron, 30 min)
  └─ label invoice ─► invoice extraction (PDFs to the model) ─► invoices ─┐
                                                                         ├─► matching ─► paid / suggestion
Bank sync (cron, 3 a day, or Sync now)                                   │
  └─ Enable Banking: N26 main, ING, PayPal ─► transactions ──────────────┘

Dashboard or chat ─► payment draft ─► owner ticks "checked" ─► Approve ─► GiroCode QR ─► bank app
                                       (the debit arrives with a later sync and is matched)
```

- **Components:** an Enable Banking client and sync command; an extraction step in email ingest plus a backfill command; matching after ingest, sync, and field edits; a Finance API (invoices, transactions, accounts and consent, payment drafts); a Finance chat agent beside the email agent; `/finance` pages for invoices, accounts, transactions and chat.
- **Data model:** bank connections, accounts, transactions, invoices (several per email, each linked to its email and PDF), matches, payment drafts, chat cards, job-run log. Every table gets RLS in its migration.
- **Access:** `finance_owner_user_id` names the single owner; every Finance route returns 403 to anyone else; Finance is off when the setting is missing.
- **Failure modes:** expired or revoked consent shows Reconnect, the sync skips that bank, and the owner gets emails at 14 days, 3 days and on expiry (Yahoo SMTP, stdlib); Reconnect all renews every bank in one sitting. Failed syncs and extractions go to the job-run log; failed extractions are `needs_info`. At most one open payment draft per invoice; Approve re-checks the invoice; only a match or the owner marks it paid.
- **Privacy:** no content reaches Langfuse; Finance traces keep models, tools, tokens, timings and errors only. Full content goes to a local trace output when a local-only setting is on; the API refuses to start with it in production. Rejected: pattern masking and a Langfuse debug switch. The Enable Banking key lives only on the owner's laptop and in Railway's variables.
- **Configuration and deployment:** settings for Enable Banking (app id, PEM contents, redirect URL), the owner, the extraction model, and local tracing; two Railway cron services; redirect URLs for the deployed frontend and local work. Enable Banking accepts only https redirect URLs, localhost included (found in 001/07), so local work runs the Vite dev server on https with a self-signed certificate. New dependencies: `pyjwt` and `cryptography` pinned directly, `segno` for QR codes.

## Success criteria

1. A real invoice email appears in Finance within 30 minutes with payee, IBAN, amount and reference, or as `needs_info`.
2. An invoice paid through its QR turns paid on its own after the next bank sync.
3. A spot check of the last 90 days shows every invoice as matched, suggested, or genuinely open.
4. An expiring connection triggers emails at 14 and 3 days and a warning, and Reconnect all restores every connection without losing history.
5. In chat, "what do I still need to pay?" and "pay them all from N26" show invoice and payment cards, and nothing can be approved there.
6. Nobody but the owner can reach a Finance route or see the Finance card.
7. The owner's hand test of real invoices finds the extracted values correct.

## Tasks

Before 001/05: [eval plan 004 — content-free tracing](../../../02-evaluation/plans/004-content-free-tracing/README.md), tasks 01–03.

- [ ] [001/01 — Privacy and terms pages](tasks/01-legal-pages.md)
- [ ] [001/02 — Email ingest runs on a schedule](tasks/02-scheduled-email-ingest.md)
- [x] [001/03 — Finance agent shell, owner only](tasks/03-finance-shell.md)
- [x] [001/04 — Invoices move from Email to Finance](tasks/04-invoices-move.md) — after 03
- [ ] [001/05 — Payment data extracted from invoice emails](tasks/05-invoice-extraction.md) — after 04, tracing change
- [ ] [001/06 — Invoice dashboard with extracted fields](tasks/06-invoice-dashboard.md) — after 05
- [x] [001/07 — Connect bank accounts through Enable Banking](tasks/07-bank-connection.md) — after 03
- [ ] [001/08 — Transactions sync from all connected accounts](tasks/08-transaction-sync.md) — after 07, 02
- [ ] [001/09 — Invoices matched to transactions](tasks/09-matching.md) — after 06, 08
- [ ] [001/10 — Pay invoices with a GiroCode QR](tasks/10-qr-payments.md) — after 09
- [ ] [001/11 — Consent expiry alerts and Reconnect all](tasks/11-expiry-alerts.md) — after 08
- [ ] [001/12 — Finance chat with cards](tasks/12-finance-chat.md) — after 10, tracing change
- [ ] [001/13 — Finance overview and end-to-end check](tasks/13-overview.md) — after all

```text
03 ─┬─► 04 ─► 05 ─► 06 ─┐
    │                   ├─► 09 ─► 10 ─► 12 ─► 13
    └─► 07 ─► 08 ───────┘
02 ─────────► 08 ─► 11
01  (independent)
```

Critical path: 03 → 07 → 08 → 09 → 10 → 12 → 13. The invoice line (04 → 05 → 06) runs alongside the bank line (07 → 08); 01, 02 and 11 fit anywhere their dependencies allow. 07 goes early because it is the most uncertain (the localhost redirect).

## Open questions and risks

- **Wrong extracted amounts,** guarded only by the owner's tick. Next action: the hand test in 001/13; add the second extraction if it finds errors.
- **Enable Banking's free mode changes or ends.** Next action: none until it happens; the client is the only provider-specific code.
- **Duplicates where banks give no id:** the fallback key assumes banks return a day's rows in a stable order. Next action: 001/08's second-run check.
- **Consent friction:** three approvals every 180 days; one ING attempt failed with `invalid_grant` and a fresh link worked. Next action: 001/11.
- **For plan 002:** paying "from a Space" is a move to the main account and then a payment from it; plan 002 chooses between Spaces as budgets and suggesting the Space's category for the next matching payment.

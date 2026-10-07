# 001 — Finance agent: invoices, bank sync, and payments

- Created: 2026-10-06
- Status: Discovery
- Current stage: 2, Research and educate

## Approval state

Settled in chat on 2026-10-06: Finance is its own agent with its own threads; bank and PayPal data come from live APIs, not file exports; invoices are paid by SEPA bank transfer to an IBAN; every payment is confirmed by the user in the bank app.

Confirmed on 2026-10-06: the problem, goals and non-goals below (Stage 1). PayPal, transfer linking, categorization and the spending view move to a separate plan 002, not yet started.

Decided on 2026-10-07: invoices move from the Email agent to Finance (see Decisions).

Awaiting: agreement on the decisions to settle in Stage 3.

[../../spec.md](../../spec.md) is an earlier draft written before discovery. It is input for later stages and will be folded into this file and deleted.

## Problem

Invoices arrive by email and get the `invoice` label, but nothing tracks whether they are paid. Checking means opening each PDF and searching two banking apps (N26, ING) by hand, and paying means copying IBAN, amount and reference into an app. The user wants one place that shows which invoices are still open, marks them paid when the money has left, and prepares the payment for the ones that are not, from a dashboard or from chat.

## Current system

- **Invoices:** email ingest labels a message `invoice` with one Jev decision ([labels.py](../../../../backend/ingest/email/labels.py)) and stores every PDF attachment as bytea in `email_attachments` ([pipeline.py](../../../../backend/ingest/email/pipeline.py)). Nothing is extracted from them. PR #1 (`feat/email-finish`, open) adds an Invoices list in the Email sidebar, an invoice page with the stored PDFs (`/email/invoices/:emailId`), and an owner-only attachment endpoint; Finance builds on it.
- **Extraction pattern:** newsletter extraction ([news.py](../../../../backend/ingest/email/news.py)) is a structured LLM call with its own model and reasoning-effort settings in [config.py](../../../../backend/app/config.py), and has an extraction benchmark (eval plan 003). Invoice extraction can follow both.
- **Agents:** `chat_threads.agent` is checked to `documents`, `email` ([thread.py](../../../../backend/app/database/models/chat/thread.py)); the picker reads [agents.ts](../../../../frontend/src/lib/agents.ts). A third agent is a new value, a sibling of `app/email_assistant/`, and a picker card.
- **Scheduling:** none. Email ingest is a manual CLI (`python -m ingest.email`). Railway runs one service, the API ([railway.json](../../../../backend/railway.json)).
- **Banks and PayPal:** no integration.
- **Memory:** [04-memory](../../../04-memory/spec.md) (draft) plans thread history and long-term memory for the existing agents. A Finance agent would need the same.

## Goals and non-goals

Goals:

- Every invoice email has its payment data (payee, IBAN, amount, reference, due date) extracted, editable, and checked.
- Transactions from N26 and ING arrive on a schedule without manual export.
- An invoice turns paid when a matching debit appears, or when the user marks it.
- The user can select open invoices, pick an account, review the prepared payments beside the invoice, and approve; the money moves only after confirmation in the bank app.
- The Finance chat answers "what do I still need to pay?" and prepares payments, but cannot approve them.
- Email ingest runs on a schedule instead of by hand.

Non-goals (this plan):

- Paying through a bank API without the user confirming in the bank app.
- Partial payments, one transaction paying several invoices, and non-EUR invoices.
- Budgets, alerts, and multi-user finance.
- PayPal, transfer linking, categorization and spending (plan 002).

## Key concepts

- **PSD2 account access.** EU banks must give licensed providers API access to account data with the customer's consent. Enable Banking holds that licence; this app is its client and never sees bank logins. Sources in [research.md](research.md).
- **Consent session.** The user is sent to the bank's own page to approve access, and comes back with a code that becomes a `session_id`. N26, ING and PayPal (DE) all allow sessions of up to 180 days. After that the user approves again; there is no silent refresh.
- **Restricted mode.** Enable Banking is free when the app only reads accounts the developer linked in its control panel first. Unlinked accounts return nothing. The in-app consent flow is still needed to get a session.
- **Request signing.** Every API call carries a JWT signed RS256 with the app's private key (`kid` = app id, lifetime at most 24 hours).
- **Unattended access limit.** Without the user present, a provider may read an account about 4 times a day. A sync started by the user in the UI does not count against this.
- **Transactions.** Each has an amount plus a credit/debit indicator, booking and value dates, a status (booked or pending), counterparty name and account, remittance text, and optionally a bank code and merchant category code. Ids (`entry_reference`, `transaction_id`) are not guaranteed by every bank, so deduplication may need a fallback key. Pending entries can change or vanish before booking.
- **EPC QR code (GiroCode).** A European standard QR code holding a SEPA transfer: name, IBAN, optional BIC, amount, reference. The N26 and ING apps both scan it, or import it from a photo, and pre-fill a transfer that the user confirms.
- **Payment initiation.** Enable Banking also has `POST /payments`: the app sends the transfer and the user confirms it at the bank. It removes the scanning step but adds a second integration.
- **Railway cron.** A cron service runs a command on a UTC schedule at least 5 minutes apart and must exit when done. Railway skips a run while the previous one is still active.

## Decisions

- **Invoices live in Finance.** The invoice list and page that PR #1 adds to the Email agent move to Finance, which adds payment status, extracted fields and payment actions. Rejected: keeping them in Email and linking across agents, which would split one invoice over two agents. Reversible: it is a matter of routes and sidebar links.

## Open questions

Decisions for Stage 3 (proposed order):

1. **How payments leave:** EPC QR code first, payment initiation later; or payment initiation now.
2. **How invoices are read:** send the PDF to the model directly, or extract text first.
3. **When an invoice counts as paid:** auto-mark on a strong match, or always ask the user to confirm.
4. **How chat shows results:** cards that show current data, or text only for now.
5. **Schedules:** email ingest every 30 minutes; bank sync 3 times a day.

Follow-ups:

- **Enable Banking privacy and terms URLs are placeholders.** The application was registered on 2026-10-07 with `https://github.com/borbalita/folio` as both URLs. Next action: write `docs/legal/privacy.md` (single-user project; data read from N26, ING and PayPal through Enable Banking; stored in Supabase, never shared; consent expires after 180 days and can be revoked; contact email) and `docs/legal/terms.md` (personal, non-commercial, no warranty), merge them, and replace both URLs in the Enable Banking control panel with their `blob/main` links. This becomes a task in Stage 5.

Unknowns:

- What do real N26 and ING transactions contain: stable ids, counterparty IBAN on transfers, readable remittance text, how far back the first sync reaches? Settled by a data check against the user's own accounts before Stage 4.

# 001 — Finance agent: invoices, bank sync, and payments

- Created: 2026-10-06
- Status: Discovery
- Current stage: 5, Decompose and validate

## Approval state

Settled in chat on 2026-10-06: Finance is its own agent with its own threads; bank and PayPal data come from live APIs, not file exports; invoices are paid by SEPA bank transfer to an IBAN; every payment is confirmed by the user in the bank app.

Confirmed on 2026-10-06: the problem, goals and non-goals below (Stage 1). PayPal linking, transfer linking, categorization and the spending view move to a separate plan 002, not yet started. Changed on 2026-10-08 at the user's request: syncing PayPal transactions moved into this plan.

Decided on 2026-10-07: invoices move from the Email agent to Finance. Decided on 2026-10-08: the N26 main account, ING and PayPal are synced in this plan, N26 Spaces are not; payments leave through a GiroCode QR after an explicit check against the invoice; a strong match marks an invoice paid automatically; invoice PDFs go to the model as files; email ingest every 30 minutes and bank sync three times a day; the chat answers with cards (see Decisions).

Confirmed on 2026-10-08: Stage 2 is complete; Stage 3 settles the decisions listed in Open questions. The data-check consent sessions were closed the same day.

Approved on 2026-10-08: the full set of decisions below (Stage 3).

Approved on 2026-10-08: the design, success criteria and risks below (Stage 4).

Awaiting: the task breakdown (Stage 5).

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
- Transactions from the N26 main account, ING and PayPal arrive on a schedule without manual export.
- An invoice turns paid when a matching debit appears, or when the user marks it.
- The user can select open invoices, pick an account, review the prepared payments beside the invoice, and approve; the money moves only after confirmation in the bank app.
- The Finance chat answers "what do I still need to pay?" and prepares payments, but cannot approve them.
- Email ingest runs on a schedule instead of by hand.

Non-goals (this plan):

- Paying through a bank API without the user confirming in the bank app.
- Partial payments, one transaction paying several invoices, and non-EUR invoices.
- Budgets, alerts, and multi-user finance.
- Linking PayPal payments to the bank debits that fund them, transfers between own accounts, N26 Spaces, categorization and spending (plan 002).

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
- **This plan syncs the N26 main account, ING and PayPal, all through Enable Banking.** One ledger of all three is the base for plan 002, and PayPal needs no separate API because Enable Banking covers it. PayPal entries carry only a transaction date, which the sync uses as the booking date. N26 Spaces are not synced: they have no IBAN and no payments of their own. Rejected: syncing Spaces now, which only matters for spending (plan 002). Reversible: the Spaces are already in the N26 consent.
- **Payments leave through an EPC QR code (GiroCode).** Approving a payment shows a QR code that the user scans in the N26 or ING app and confirms there; copy buttons for IBAN, amount and reference are the fallback. Approve is enabled only after the user ticks that payee, IBAN, amount and reference match the invoice, which is shown beside the payment. Rejected for now: payment initiation through Enable Banking, which the application cannot use (only the `AIS` service is enabled; a test request on 2026-10-08 returned `403 ACCESS_DENIED`). Reversible: payment initiation can replace the QR step later if Enable Banking enables `PIS`.
- **A strong match marks an invoice paid automatically.** A debit with the invoice's amount and either its IBAN or its reference links the invoice and marks it paid; a debit with the amount and a similar payee name is a suggestion the user confirms or rejects. Automatic links are labelled and undone with one click. Rejected: confirming every match, because outgoing transfers in the real data always carry IBAN and reference, so strong matches are reliable and confirming them is busywork.
- **Invoice PDFs go to the model as files.** One structured call per invoice email receives the stored PDFs as file input, so scanned invoices work and no PDF library is added. The model is its own setting, like newsletter extraction, so a cheaper one can be benchmarked later. Rejected: extracting text locally first, which adds a dependency and fails on scans.
- **One extraction call on `gpt-6.1-sol`, checked by rules and by hand.** `gpt-6.1-sol` matched GPT-6 Astra on every newsletter item in eval plan 003, and at a few invoices a month its cost is negligible; it is set through its own setting, with `gpt-6-astra` the next option if hand testing finds it weak. The IBAN checksum, plausibility checks, the user's tick against the invoice, and the bank's payee-name check guard the values; the amount is the field only the tick protects, so the payment card shows it most prominently. The owner tests extraction by hand once the feature is built; there is no benchmark. Rejected for now: a second, independent extraction compared field by field, added if hand testing shows wrong amounts.
- **Email ingest runs every 30 minutes; bank sync three times a day.** Both are Railway cron schedules (UTC, so local times shift by an hour with daylight saving). Three bank syncs stay under the PSD2 limit of about four unattended reads per account per day; a manual Sync now covers the rest. Reversible: a schedule setting.
- **The Finance chat answers with cards.** A reply can carry invoice lists and payment cards built from the same components as the invoices page, including the QR code and the check against the invoice. Cards reference invoices and payments by id and show their current state. Chat tools can prepare payments but never approve them. Built after the invoices page and payment cards, so the chat reuses them. Rejected: text-only answers with links, which would send "pay them all" off to another page.

## Design

### Components and data flow

```text
Email ingest (cron, 30 min)
  └─ label invoice ─► invoice extraction (PDFs to the model) ─► invoices ─┐
                                                                         ├─► matching ─► paid / suggestion
Bank sync (cron, 3 a day, or Sync now)                                   │
  └─ Enable Banking: N26 main, ING, PayPal ─► transactions ──────────────┘

Dashboard or chat ─► payment draft ─► user ticks "checked" ─► Approve ─► GiroCode QR ─► bank app
                                       (the debit arrives with a later sync and is matched)
```

- **Bank sync:** an Enable Banking client (signed requests, consent flow, paginated transactions) and a sync command for the cron service and Sync now. Stores booked entries only, deduplicated by the bank's id where present and otherwise by date, amount, counterparty, text and an ordinal.
- **Invoice extraction:** one step in email ingest after labelling, plus a backfill command for invoices already stored. One email can hold several invoices; each invoice links to its email and, when it has one, its PDF.
- **Matching:** runs after email ingest, bank sync, and an edit of an invoice's fields.
- **Finance API:** invoices, transactions, accounts and the consent flow, payment drafts and approval. PR #1's invoice routes and attachment endpoint move here; old `/email/invoices/...` links redirect.
- **Finance chat agent:** a sibling of the email agent, with tools that list and prepare but never approve, and cards stored per message.
- **Access:** a `finance_owner_user_id` setting names the single owner. Every Finance route returns 403 to anyone else, and Finance is off for everyone when the setting is missing. Invoices come only from mailboxes that user owns.
- **Data model:** bank connections, accounts, transactions, invoices, invoice–transaction matches, payment drafts, chat cards, and a job-run log. Every table gets RLS in its migration.
- **Frontend:** `/finance` with the invoices list, an invoice page with the payment panel, accounts with connect and reconnect, a plain transactions list, and the chat.

### Failure modes, privacy and secrets

- **Consent expiry or revocation:** the account shows Reconnect, the scheduled sync skips it and keeps syncing the others, and Finance warns 14 days before `valid_until`.
- **Failed sync or extraction:** recorded in the job-run log; other accounts and emails continue. An invoice whose extraction failed or lacks a valid IBAN and amount is `needs_info`.
- **Unclear payment state:** at most one open payment draft per invoice. Approve re-checks the invoice before showing the QR. An invoice turns paid only through a match or the user's click, never because a QR was shown.
- **Tracing:** no content reaches Langfuse. Finance agents are instrumented without content or binary content, so traces keep models, tool names, token counts, timings and errors, but no prompts, messages, tool data or PDFs; other parties' data (payees, senders, references) never leaves the app. For debugging, a local-only setting writes full content to a local trace output; the API refuses to start with it in production. Rejected: masking by pattern (names and free text have no pattern) and a debug switch that sends full content to Langfuse. The same rule for the email agent, and deleting its existing content traces, is a separate change done before this plan's work.
- **Secrets:** the Enable Banking private key lives only on the user's laptop and in Railway's variables, never in the repository or the database.

### Configuration and deployment

- **Settings** in `backend/app/config.py`: Enable Banking app id, private key (PEM contents) and redirect URL; `finance_owner_user_id`; the invoice extraction model and effort; the local-only trace setting. The API starts without the Enable Banking and extraction settings; the sync and extraction commands stop with a clear error when one is missing.
- **Enable Banking redirect URLs:** the deployed frontend's `/finance/accounts/callback` is registered, and `http://localhost:5173/finance/accounts/callback` for local work (only the `https` localhost address is registered today). If Enable Banking accepts only https, the consent flow is tested on the deployed app.
- **Railway:** two cron services from the same code, email ingest every 30 minutes and bank sync three times a day, plus the new variables on the backend service. Railway skips a run while the previous one is still active.
- **Dependencies:** `pyjwt` and `cryptography` pinned directly to sign Enable Banking requests (both already installed through `supabase`); `segno` to render QR codes (pure Python, no further dependencies).

## Success criteria

1. A real invoice email appears in Finance within 30 minutes with payee, IBAN, amount and reference, or as `needs_info` when the invoice has no IBAN.
2. An invoice paid through its QR code turns paid on its own after the next bank sync.
3. For the last 90 days, a spot check shows every invoice as matched, suggested, or genuinely open.
4. An expiring connection shows a warning, and Reconnect restores it without losing history.
5. In chat, "what do I still need to pay?" and "pay them all from N26" show invoice and payment cards, and nothing can be approved from the chat.
6. Nobody but the owner can reach any Finance route or see the Finance card.
7. The owner's hand test of real invoices finds the extracted values correct.

## Risks

- **Wrong extracted values,** above all the amount, which only the user's tick guards. Hand testing decides whether a second extraction is needed.
- **Enable Banking's free restricted mode changes** or ends; the sync would need another provider or a paid plan.
- **Duplicate transactions** where banks give no id; the fallback key with an ordinal relies on banks returning rows in a stable order.
- **Consent friction:** three bank approvals every 180 days, and one ING attempt already failed once with `invalid_grant`.

## Open questions

Answered by the real data check (2026-10-08, details in [research.md](research.md#real-data-check-2026-10-08)):

- Invoice payments are transfers, and transfers from both banks carry the counterparty IBAN and the remittance text, so matching on amount plus IBAN or reference is feasible. Card payments and direct debits carry neither.
- Transaction ids are missing on N26 transfers and not unique on N26 refunds, so deduplication needs a fallback key with an ordinal.
- N26 returns 9 Spaces next to the main account; they have no IBAN and almost no activity.
- PayPal ↔ N26 linking on amount and a 0–5 day window finds a single candidate in 31 of 32 cases (plan 002).

For plan 002:

- **N26 Spaces as a category hint.** Paying "from a Space" is a move from the Space to the main account, then a payment from the main account; no payment is made directly from a Space. The moves are visible on both sides (same day and amount, no counterparty name) and are transfers. Plan 002 chooses between Spaces as budgets (money moved out vs. money spent per category) and suggesting the Space's category for the next matching payment, confirmed by the user.

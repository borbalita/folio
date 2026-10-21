# 003 — Finance demo: a demo user with fake invoices and a live run

- Created: 2026-10-20
- Status: Ready
- Current stage: Spec approved; implementation not started

## Approval state

- 2026-10-20: settled in chat, one question at a time: the demo is shown live by the owner first and may become self-serve later; it shows a ready-made state plus one invoice that arrives live; the live invoice skips the mailbox and enters the real pipeline; the demo is a second user in the production app; invoices come from a fixed catalogue of fictional vendors; a simulated bank booking closes the payment loop; the controls sit on a separate presenter page; reset is a button there plus a command. Design sections 1–4 approved.
- 2026-10-20: written spec and task breakdown approved; the plan is Ready.
- 2026-10-21: added while planning 003/01, at the owner's OK: the demo user's Accounts page shows only the demo bank; sync and expiry checks skip it; Connect returns 403 for the demo user.

## Problem

The owner wants to show the Finance agent to clients and recruiters. Their own account holds real invoices and bank data, so it can't be shown. There is no way to see the agent with data that is fake but realistic, and no way to show the moment that makes it interesting: an invoice email arriving, being recognized and extracted, paid by QR, and matched to the bank booking.

## Current system

- **Access:** Finance is open to one user, `finance_owner_user_id` ([finance_access.py](../../../../backend/app/auth/finance_access.py)). The Email agent is open to anyone who owns an active mailbox ([email_access.py](../../../../backend/app/auth/email_access.py)).
- **Mail:** one Yahoo mailbox. `ingest_fetched` upserts the Yahoo mailbox and passes the parsed messages to `ingest_messages`, which labels, checks, extracts, embeds and stores them ([pipeline.py](../../../../backend/ingest/email/pipeline.py)); `match_for_user` runs after ingest ([run.py](../../../../backend/ingest/email/run.py)). Mailbox providers are checked to `yahoo` and `gmail` ([mailbox.py](../../../../backend/app/database/models/email/mailbox.py)).
- **Invoices:** each belongs to an email, and the email to a mailbox and its user. Extraction sends the PDF to the model as a file; no PDF library is a runtime dependency.
- **Bank:** connections, accounts and transactions per user ([models/finance](../../../../backend/app/database/models/finance)). The bank-sync cron only syncs `finance_owner_user_id` ([ingest/bank/run.py](../../../../backend/ingest/bank/run.py)).
- **Matching and payments:** a debit with the invoice's amount and IBAN or reference links the invoice and marks it paid; the link completes its payment draft ([matches.py](../../../../backend/app/database/matches.py), [payments.py](../../../../backend/app/database/payments.py)).
- **Frontend:** the invoice list, invoice page, payments and transactions load once when the page opens.
- **Sign-up** is off in Supabase; users are created in the Supabase dashboard.

## Goals and non-goals

Goals:

- A demo user sees Finance with about 10 realistic invoices and 3 months of transactions, all fictional.
- During a demo, the owner sends a new invoice that goes through the real pipeline and appears in the app on its own.
- The owner pays it by QR, simulates the bank booking, and the invoice turns paid through the real matching.
- One click returns the demo to its base state, with dates relative to today.
- The audience sees only the normal app; the controls are on a separate page.
- The owner's data can't be reached or changed by anything in the demo.

Non-goals: a public, self-serve demo (later, see risks); a separate demo environment; real email delivery; LLM-written invoices; a daily cost limit; demo data for the Email or Documents agents.

## Decisions

- **The demo is a second user in the production app,** named by `DEMO_USER_ID`. Rejected for now: a separate Railway environment and Supabase project, which isolates fully but doubles hosting and deploys. Reversible: if the demo becomes self-serve, the demo user moves to its own environment; reset already rebuilds everything from code.
- **The live invoice skips the mailbox** and is handed to the same `ingest_messages` path that Yahoo mail uses, with a demo mailbox. Rejected: a real second mailbox, which needs credentials and a manual ingest trigger, and waits for delivery.
- **Invoices come from a fixed catalogue of fictional vendors** with fresh amounts, numbers, dates and IBANs each time. Sender domains use the reserved `.example` TLD, so no real company or domain is imitated. Rejected: LLM-written invoices (cost, unpredictable, tests extraction against the model's own text) and hand-made PDFs (fixed content, duplicates).
- **A small PDF writer of our own** renders the invoice as text and lines (about 50 lines, no new dependency). Rejected: adding reportlab or fpdf2 for one page of text.
- **The base state is written as finished rows,** with no model calls, so a reset is fast, free and the same every time. Only the live invoice uses the models.
- **A simulated bank booking closes the loop:** it writes the debit of an approved payment into the demo account and runs the existing matching.
- **The controls live on a presenter page** (`/finance/demo`), not in the app the audience sees. Rejected: a keyboard-shortcut overlay and a corner button, both visible when used.
- **Lists refresh every 5 seconds while visible and on focus, for every user.** Rejected: refreshing only for the demo user, which adds a special case for no saving.

## Design

```text
Presenter page (/finance/demo, phone or 2nd tab)          The app the audience sees (/finance)
  ├─ New invoice ──► email builder ──► ingest_messages ──► invoices ──┐   lists refresh every 5 s
  │                  (catalogue, PDF)   label, check,                 │
  │                                     extract, embed                ├──► matching ──► paid
  ├─ Book payment ─► debit in demo account ───────────────────────────┘
  └─ Reset ───────► delete the demo user's rows ─► write the base state
```

- **Demo user and access:** the owner creates the user in the Supabase dashboard; its id goes to Railway as `DEMO_USER_ID`, mirrored in `config.py` and optional (no demo without it). Finance access becomes "owner or demo user". Every demo route takes the user id from `DEMO_USER_ID` only and returns 403 to anyone else, the owner included.
- **Demo mailbox and bank:** a mailbox with a new provider `demo` (no IMAP; the email cron never reads it), which doesn't open the Email agent. One bank connection `Demo Bank` with one account, "Girokonto" with a fake IBAN, and consent far in the future. Bank sync (cron and Sync now) and expiry notices only cover the real banks (N26, ING, PayPal), so the demo connection never reaches Enable Banking; Sync now for the demo user adds nothing. The demo user's Accounts page lists only the demo bank, and Connect returns 403 for the demo user.
- **Code:** a package `backend/app/demo/`: `catalogue.py` (vendors), `pdf.py` (PDF writer), `emails.py` (builds a parsed message with its PDF), `base_state.py` (the rows below), `reset.py`, `booking.py`; routes under `/finance/demo`; a command `python -m app.demo.reset`.
- **Base state** (offsets from today, turned into dates at reset):

  | Status | Count |
  |---|---|
  | Open, due soon | 2 |
  | Open, overdue | 1 |
  | Paid, matched automatically | 3 |
  | Possible payment found | 1 |
  | Paid before it arrived | 1 |
  | Needs info (online only) | 1 |

  Plus about 40 transactions over 90 days (salary, rent, shops, all fictional) and the debits behind the matches.
- **Reset:** one database transaction deletes the demo user's invoices, matches, payment drafts, transactions, emails with attachments and chunks, and Finance chat threads, then writes the base state. A failure changes nothing.
- **New invoice:** the presenter picks Normal, Already paid, Online only or Random. The builder draws a vendor, an amount, an invoice number, dates and an IBAN with a valid checksum, and writes a German subject, body and `Rechnung_<number>.pdf`; Already paid says the amount was debited, Online only has no IBAN and points to the customer account. The message gets a fresh Message-ID and goes to `ingest_messages` with the demo mailbox, then `match_for_user` for the demo user. The request waits for the model calls (about 10–20 s) and returns the stored invoice. Traces stay content-free and carry the tag `demo`.
- **Book payment:** the presenter page lists the demo user's approved payments. Book writes a booked debit (amount, payee, IBAN, reference, today) into the demo account and runs `match_for_user`; the strong match marks the invoice paid and completes the payment.
- **Presenter page:** phone-sized, three blocks: New invoice (kind, Send, a log of recent sends), Payments to book, Reset demo (with confirmation). Not in the sidebar.
- **Refresh:** invoice list, invoice page, payments and transactions refetch every 5 s while the tab is visible and on window focus.
- **Failure modes:** a model error on a new invoice shows on the presenter page and stores what the pipeline stores today (`needs_info`); Book on a payment that was already booked does nothing; without `DEMO_USER_ID`, the demo routes return 404 and nothing else changes.

## Success criteria

1. After a reset, the demo user sees the base state in Finance, and nothing of the owner's.
2. A sent invoice appears in the app within 30 seconds without a manual reload.
3. Pay, Approve and Book turn the new invoice paid, labelled as matched automatically.
4. A reset after a demo returns exactly the base state, with current dates.
5. Nothing in the demo can read or change another user's data, and the owner can't trigger a demo route.
6. The owner runs one rehearsal on laptop and phone and finds it presentable.

## Tasks

- [ ] [003/01 — Demo user, access, demo mailbox and bank](tasks/01-demo-user.md)
- [ ] [003/02 — Vendor catalogue, PDF writer and email builder](tasks/02-invoice-builder.md)
- [ ] [003/03 — Base state and reset](tasks/03-base-state-reset.md) — after 01, 02
- [ ] [003/04 — Live invoice through the pipeline](tasks/04-live-invoice.md) — after 01, 02
- [ ] [003/05 — Simulated bank booking](tasks/05-bank-booking.md) — after 01
- [ ] [003/06 — Presenter page and list refresh](tasks/06-presenter-page.md) — after 03, 04, 05
- [ ] [003/07 — Production setup and rehearsal](tasks/07-rehearsal.md) — after 06

```text
01 ─┬─────────► 05 ─┐
    ├─► 03 ─────────┼─► 06 ─► 07
02 ─┴─► 04 ─────────┘
(03 and 04 need both 01 and 02)
```

Critical path: 01 → 04 → 06 → 07. 02 can start beside 01; 03, 04 and 05 are independent of each other.

## Open questions and risks

- **Self-serve later:** strangers would use the demo login. Before that: a daily limit on new invoices, a nightly reset cron (the same reset function), a visible guide instead of the presenter page, and moving the demo to its own environment.
- **Demo data in the production database,** separated by user filters and RLS. Guarded by tests that reset leaves other users' rows untouched and that demo routes refuse everyone but `DEMO_USER_ID`.
- **Model output on fictional invoices** may differ from real ones (for example, Jev not labelling a fictional vendor as an invoice). Next action: 003/04 checks each kind against the real models before the presenter page is built.
- **Live timing:** 10–20 seconds of model calls during a call. Next action: the rehearsal in 003/07 measures it; if it feels long, the presenter page sends earlier or the invoice list shows a "processing" row.

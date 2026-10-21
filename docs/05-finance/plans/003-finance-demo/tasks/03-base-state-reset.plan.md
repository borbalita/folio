# 003/03 Base state and reset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One call deletes everything the demo user owns in Finance and writes a fixed, realistic base state whose dates are relative to today.

**Architecture:** A pure builder turns `today` and the demo account ids into ORM rows (emails with PDFs from 003/02, invoices, transactions, matches), with ids assigned up front so rows can reference each other. A reset function deletes by the demo mailbox, the demo account and the demo user's Finance threads (database cascades take invoices, matches, drafts, attachments, chunks and messages), adds the rows, and commits once. A route and a command call it.

**Tech Stack:** SQLAlchemy 2.1 sessions, FastAPI, pytest.

**Spec:** [../README.md](../README.md), task [03-base-state-reset.md](03-base-state-reset.md).

## Global Constraints

- No model calls and no network: the base state is finished rows.
- Everything is scoped by the demo user: the demo mailbox id and demo account id from `ensure_demo_accounts(session, user_id)` (003/01), and `ChatThread.user_id == user_id AND agent = 'finance'`. Nothing else is deleted.
- One transaction: `reset_demo` never commits halfway; the caller commits; any error leaves the old state.
- Vendors, counterparties and the employer are fictional (as in 003/02; never a real company name); IBANs for counterparties that aren't catalogue vendors also use a `0` bank code via `demo_iban`.
- Dates come from `today` only (`datetime.now(ZoneInfo(settings.email_timezone)).date()` at the edges, as `app/demo/booking.py` does).
- Tests: from `backend/`, `set -a && . ./.env.example && set +a && EMAIL_RERANK=false OPENAI_API_KEY=sk-invalid-for-tests uv run pytest -m "not integration"`; `uv run ruff check .`. Test module names must be unique across `tests/` (no packages): use `test_demo_base_state.py`, `test_demo_reset.py`.

## Review Focus

1. **The base state re-matches on the next Book.** `match_for_user` runs after every demo booking; a base debit that happens to fit an open invoice would silently link it → test in Task 1 that `app.finance.matching.propose` over the base state's open invoices and debits proposes no link and no suggestion other than the seeded one.
2. **Reset on the 31st or near a month start**: offsets must not produce invoice dates after today or due dates before invoice dates → test in Task 1 over several `today` values (month ends, 1 March, a leap day).
3. **A second reset right after the first** must not fail on unique constraints (`uq_emails_mailbox_message_id`, `uq_transactions_account_id_dedup_key`, `uq_invoices_email_id_position`) → fresh Message-IDs per build and dedup keys derived from a per-build id; test in Task 1 that two builds share no Message-ID or dedup key.
4. **A reset while a payment is approved** (presenter pressed Approve, then Reset) must delete the draft too → covered by the cascade from invoices; test in Task 2 that no statement targets drafts directly and that the email delete is scoped to the demo mailbox (the cascade does the rest).
5. **The command run before the demo user ever signed in** has no `users` row → the command exits with a clear message instead of a foreign-key error; test in Task 2.

---

### Task 1: The base state as rows

**Files:**
- Create: `backend/app/demo/base_state.py`
- Test: `backend/tests/demo/test_demo_base_state.py`

**Interfaces:**
- Consumes: `VENDORS`, `demo_iban` (`app/demo/catalogue.py`); `draw_invoice`, `invoice_message`, `DemoInvoice`, `InvoiceKind` (`app/demo/emails.py`); `DemoAccounts(mailbox_id, account_id)` (`app/demo/accounts.py`); `content_hash` (`ingest/email/parse.py`); models `EmailMessage`, `EmailAttachment`, `Invoice`, `InvoiceMatch`, `Transaction`; `InvoiceStatus`, `MatchStatus`, `MatchSource`, `PAID_BY_MATCH`, `PAID_BY_INVOICE`, `EmailLabel.INVOICE`.
- Produces:
  - `@dataclass(frozen=True, slots=True) class BaseRows: emails: list[EmailMessage]; attachments: list[EmailAttachment]; invoices: list[Invoice]; transactions: list[Transaction]; matches: list[InvoiceMatch]` with `def all(self) -> list[object]` in insert order (emails, attachments, invoices, transactions, matches).
  - `build_base_state(today: date, accounts: DemoAccounts, *, to_address: str) -> BaseRows`.
  - `BASE_INVOICES`: the spec's table as data, one entry per invoice: `(vendor key, kind, role, invoice_days_ago, due_in_days)`; role is one of `open`, `matched`, `suggested`, `paid_before`, `online`:

    | # | vendor | kind | role | invoice date | due |
    |---|---|---|---|---|---|
    | 1 | mobilfunk | normal | open (due soon) | −6 | +4 |
    | 2 | strom | normal | open (due soon) | −10 | +3 |
    | 3 | fitness | normal | open (overdue) | −20 | −6 |
    | 4 | hosting | normal | matched | −40 | −33 (debit −36) |
    | 5 | strom | normal | matched | −70 | −56 (debit −60) |
    | 6 | zahnarzt | normal | matched | −55 | −25 (debit −45) |
    | 7 | handwerk | normal | suggested | −30 | −16 (debit −22) |
    | 8 | mobilfunk | already_paid | paid_before | −35 | −25 |
    | 9 | mobilfunk | online_only | online | −3 | +7 |

- Rows, per role:
  - Each invoice is `draw_invoice(random.Random(seed_i), kind, today, vendor)` with `dataclasses.replace` setting `invoice_date`, `due_date` (and `debit_date` for already_paid) from the offsets; seeds are fixed per row so the base state looks the same every time. Its email is `invoice_message(...)` with `sent_at` = invoice date 08:15 in `settings.email_timezone`; `EmailMessage` fields as `ingest/email/pipeline.py` `_store_one` writes them, `label = invoice`, no chunks. Attachments as `_write_attachments` writes them.
  - `Invoice`: `position = 0`, payee = vendor name, IBAN, amount, `currency = "EUR"`, invoice number, reference, dates, `attachment_id` of the PDF; **open** → `status = open`; **matched** → `status = paid`, `paid_by = PAID_BY_MATCH`, `paid_at` = debit date, plus a debit `Transaction` (amount = −invoice amount, counterparty = vendor name and IBAN, remittance = the reference) and an `InvoiceMatch(status = linked, source = auto, signals` as `app.finance.matching.signals` returns for that pair, i.e. amount + iban + reference)`; **suggested** → `status = open`, a debit with the same amount, counterparty "KAYA BRANDT MALERFACHBETR." (a shared name token, no IBAN, remittance "Rechnung Flur"), and an `InvoiceMatch(status = suggested, source = auto, signals` as `signals()` returns, i.e. amount + name)`; **paid_before** → `status = paid`, `paid_by = PAID_BY_INVOICE`, `paid_at` = sent_at; **online** → the placeholder the pipeline stores for `online_only`: `status = needs_info`, `issues = ["invoice_online"]`, no fields, no attachment.
  - Everyday transactions over the last 90 days (about 30; together with the 4 debits above about 34–40): each month a salary credit (+3 240,00, "Lindgrün Software GmbH", "Gehalt {Monat}"), rent (−1 150,00, "Hausverwaltung Kranich", "Miete {Monat}"); and 6–8 card debits per month from a fixed list of fictional shops ("Frischmarkt Lindenstraße", "Biomarkt am Ufer", "Apotheke am Mehringdamm", "Café Nordlicht", "Drogerie Weiss", "Buchhandlung Seitenwind"), amounts 3,50–89,00, drawn from `random.Random(2026)` so they're the same every time. `bank_code = "demo"`, `dedup_key = f"demo-base:{build_id}:{n}"` with `build_id = uuid4().hex`, `raw = {"demo_base": True}`.
  - Ids: assign `uuid4()` to every row's `id` in the builder, so invoices, attachments and matches reference each other without a flush.

- [ ] **Step 1: Write failing tests**
  - `test_base_state_counts_match_the_spec_table`: with `today = date(2026, 10, 21)`: 9 invoices; `open` with due within 7 days = 2, `open` overdue = 1, `paid` via match = 3, `open` with a suggested match = 1, `paid` by invoice = 1, `needs_info` with `invoice_online` = 1.
  - `test_dates_follow_today`: for `today` in `date(2026, 10, 21)`, `date(2026, 1, 31)`, `date(2026, 3, 1)`, `date(2028, 2, 29)`: every invoice date ≤ today, every due date ≥ its invoice date, every booking date within `[today − 90, today]`; invoice 1's due date is `today + 4` in each.
  - `test_base_state_is_realistic`: 34–40 transactions; at least 3 salary credits; every counterparty and vendor name absent from a small deny list of real brands (`"REWE"`, `"EDEKA"`, `"Telekom"`, `"Vodafone"`, `"Stadtwerke"`); every matched invoice's debit has `amount == -invoice.amount` and its remittance equals the invoice reference.
  - `test_rows_reference_each_other`: every invoice's `email_id` is an email in the build, every `attachment_id` an attachment in the build (`None` only for the online placeholder), every match's invoice and transaction in the build, every email's `mailbox_id` and transaction's `account_id` from the given `DemoAccounts`.
  - `test_matching_adds_nothing_to_the_base_state`: build `InvoiceFacts` and `Debit` values for the open invoices and all debits (as `app/database/matches.py` does) and run `propose`: the only proposal is the seeded suggestion for invoice 7.
  - `test_two_builds_do_not_collide`: two builds share no `message_id` and no `dedup_key`.
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement** `base_state.py` (row builders per role as small functions; the shop list and the table as module-level tuples).
- [ ] **Step 4: Tests and ruff green.**
- [ ] **Step 5: Commit** `feat(demo): base state as finished rows, dated from today`

---

### Task 2: Reset, route and command

**Files:**
- Create: `backend/app/demo/reset.py`
- Modify: `backend/app/api/demo.py` (add `POST /reset`)
- Test: `backend/tests/demo/test_demo_reset.py`, `backend/tests/api/test_demo_routes.py` (extend if it exists, else create)

**Interfaces:**
- Consumes: `build_base_state`, `BaseRows` (Task 1); `ensure_demo_accounts` (003/01); `require_demo_user` (`app/auth/demo_access.py`); `chats.ensure_user`; `get_session` (`app/database/engine.py`).
- Produces:
  - `reset_demo(session: Session, user_id: uuid.UUID, *, email: str, today: date) -> dict[str, int]`: `accounts = ensure_demo_accounts(session, user_id)`; `delete(EmailMessage).where(EmailMessage.mailbox_id == accounts.mailbox_id)`; `delete(Transaction).where(Transaction.account_id == accounts.account_id)`; `delete(ChatThread).where(ChatThread.user_id == user_id, ChatThread.agent == "finance")`; `session.add_all(build_base_state(...).all())`; `session.flush()`; returns `{"invoices": 9, "transactions": n}`. Does not commit.
  - `run_reset(user_id: uuid.UUID, email: str, today: date | None = None) -> dict[str, int]`: opens a session, calls `reset_demo`, commits; on any exception the session rolls back and the exception propagates.
  - `POST /finance/demo/reset` (behind `require_demo_user`): `chats.ensure_user(user.id, user.email)`, then `run_reset` in a thread; returns the counts.
  - `python -m app.demo.reset`: needs `settings.demo_user_id` (exit 1 with "Set DEMO_USER_ID first."); exits 1 with "Sign in once as the demo user first." when no `users` row exists; otherwise prints the counts.

- [ ] **Step 1: Write failing tests**
  - `test_reset_deletes_only_the_demo_users_rows`: with a fake session recording executed statements, `reset_demo` issues exactly three deletes; compiled, they filter on the demo mailbox id, the demo account id, and the demo user id with `agent = 'finance'`; none targets `payment_drafts`, `invoices` or `invoice_matches` directly (cascades), and none lacks a WHERE clause.
  - `test_reset_writes_the_base_state_and_does_not_commit`: the fake session receives `add_all` with the build's rows and no `commit`.
  - `test_run_reset_rolls_back_on_error`: a session whose `add_all` raises → `run_reset` raises, `commit` is never called, `rollback` (or the context manager's exit) runs.
  - `test_reset_route_is_for_the_demo_user_only`: 404 with no `DEMO_USER_ID`, 403 for the owner, 200 with counts for the demo user (patch `run_reset` and `chats.ensure_user`; assert `ensure_user` was called with the demo user's id and email).
  - `test_command_needs_a_demo_user`: no `DEMO_USER_ID` → exit 1 with the message; missing `users` row → exit 1 with the sign-in message.
- [ ] **Step 2: Run; expect ImportError / 404.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Full fast suite and ruff green.**
- [ ] **Step 5: Commit** `feat(demo): reset the demo user's Finance to the base state`

---

### Task 3: Verify and record (main session)

- [ ] Every `(test)` criterion in [03-base-state-reset.md](03-base-state-reset.md) maps to a passing test.
- [ ] `(browser)`: with the owner's OK (it writes the demo user's rows in the shared database), sign the owner in as the demo user locally, press reset via `POST /finance/demo/reset` from the page context, then open Invoices, Transactions and Accounts: every status from the table is visible, the PDFs open, Accounts shows Demo Bank connected. Reset a second time and check the lists look the same.
- [ ] Verified section in the task file; tick 003/03 only if all passed.

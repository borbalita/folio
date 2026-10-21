# 003/01 Demo user, access, demo mailbox and bank — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user named by `DEMO_USER_ID` can open Finance and owns a demo mailbox and a demo bank account that no cron, sync or Enable Banking call touches.

**Architecture:** One optional setting names the demo user. Finance access widens from "owner" to "owner or demo user"; a new dependency guards future `/finance/demo` routes. A new mailbox provider `demo` is excluded from Email access but included in Finance's invoice scope. A fixed connection `Demo Bank` is filtered out of sync and expiry, and is the only connection the demo user's Accounts page lists.

**Tech Stack:** FastAPI, SQLAlchemy 2.1 + Alembic, pytest, React/TS (one type).

**Spec:** [../README.md](../README.md), task [01-demo-user.md](01-demo-user.md).

## Global Constraints

- No new dependencies.
- Settings only through `backend/app/config.py`; no `os.getenv`.
- Migrations: `uv run alembic revision --autogenerate`, hand-write only what autogenerate misses (here: the check constraint). Don't apply to the shared database without asking the owner.
- Run from `backend/`: `set -a && . ./.env.example && set +a && EMAIL_RERANK=false OPENAI_API_KEY=sk-invalid-for-tests uv run pytest -m "not integration"` and `uv run ruff check .`. Frontend: `pnpm exec tsc --noEmit`, `pnpm lint`.
- Without `DEMO_USER_ID`, behaviour for every existing user is unchanged.

## Review Focus

1. **`DEMO_USER_ID` equal to `FINANCE_OWNER_USER_ID`** (a config mistake): the owner's real banks must not disappear and demo routes must not open for the owner. Settings refuse to start when they are equal → test in Task 1.
2. **Blank `DEMO_USER_ID=""` on Railway**: must mean "no demo", like the owner settings → test in Task 1.
3. **Owner's Sync now and cron after the filter**: N26, ING and PayPal must still sync and get expiry notices → test in Task 3 that the filter keeps all three.
4. **Email agent tools for a user with both a real and a demo mailbox**: email search must not include the demo mailbox → covered by `active_mailbox_ids` excluding `demo` (Task 2).
5. **Finance chat for the demo user** must see demo invoices: the Finance orchestrator uses the invoice scope, not the email scope → test in Task 2.

---

### Task 1: Demo user setting, Finance access, demo-route guard

**Files:**
- Modify: `backend/app/config.py` (field, blank validator list, owner/demo validator)
- Modify: `backend/app/auth/finance_access.py`
- Create: `backend/app/auth/demo_access.py`
- Test: `backend/tests/api/test_finance_access.py`, `backend/tests/auth/test_demo_access.py`, `backend/tests/test_config.py` (new)

**Interfaces:**
- Produces: `settings.demo_user_id: uuid.UUID | None`; `is_finance_user(user: CurrentUser) -> bool`; `require_finance_user(user: CurrentUser) -> None` (renamed from `is_finance_owner` / `require_finance_owner`; update every caller: `app/api/finance.py`, `app/auth/email_access.py`); `is_demo_user(user_id: uuid.UUID) -> bool`; `require_demo_user(user: CurrentUser) -> CurrentUser` (FastAPI dependency: 404 when unset, 403 for anyone else).

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_finance_access.py
def test_me_lists_finance_for_the_demo_user(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    assert authed_client.get("/me").json()["agents"] == ["documents", "finance"]

def test_finance_routes_answer_for_the_demo_user(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    monkeypatch.setattr(bank_connections, "list_connections", lambda user_id: [])
    assert authed_client.get("/finance/bank-connections").status_code == 200

# tests/auth/test_demo_access.py — a throwaway app with one route behind require_demo_user
def test_demo_route_is_404_without_demo_user(...): ...        # demo_user_id None → 404
def test_demo_route_is_403_for_the_owner(...): ...            # owner id == TEST_USER_ID, demo other → 403
def test_demo_route_answers_for_the_demo_user(...): ...       # demo_user_id == TEST_USER_ID → 200

# config
def test_blank_demo_user_id_is_none(): Settings(..., demo_user_id="") → None
def test_demo_user_must_differ_from_the_owner(): same uuid for both → ValidationError
```

- [ ] **Step 2: Run them; expect failures** (`AttributeError: demo_user_id`, missing module).

- [ ] **Step 3: Implement**
  - `demo_user_id: uuid.UUID | None = None` in `Settings`; add it to `blank_optional_uuid`'s field list; a `model_validator(mode="after")` raising `ValueError("DEMO_USER_ID must not be the finance owner")` when both are set and equal.
  - `finance_access.py`: `is_finance_user` = owner or demo user; `require_finance_user` raises 403 otherwise. Rename callers; the Finance router's dependency function becomes `finance_user`.
  - `demo_access.py`: `is_demo_user(user_id)` and `require_demo_user(user: Annotated[CurrentUser, Depends(get_current_user)])`.

- [ ] **Step 4: Run the full fast suite; expect all green** (existing owner tests still pass).

- [ ] **Step 5: Commit** `feat(demo): DEMO_USER_ID opens Finance and guards demo routes`

---

### Task 2: Demo mailbox provider, kept out of Email, kept in Finance

**Files:**
- Modify: `backend/app/database/models/email/mailbox.py` (`MailboxProvider.DEMO = "demo"`)
- Create: `backend/alembic/versions/<rev>_mailbox_provider_demo.py`
- Modify: `backend/app/database/mailboxes.py`
- Modify: `backend/app/auth/finance_access.py`, `backend/app/api/finance.py`, `backend/app/chat/orchestrator.py:250`
- Test: `backend/tests/api/test_email_access.py`, `backend/tests/api/test_finance_invoices.py`, `backend/tests/chat/test_finance_turn.py`, `backend/tests/database/test_mailboxes.py` (new)

**Interfaces:**
- Consumes: `require_finance_user` (Task 1).
- Produces: `mailboxes.active_mailbox_ids(user_id) -> list[UUID]` now **excludes** `demo` (Email scope, unchanged callers); `mailboxes.invoice_mailbox_ids(user_id) -> list[UUID]` all active mailboxes including `demo` (Finance scope); `require_invoice_mailboxes(user: CurrentUser) -> list[UUID]` in `finance_access.py` (403 when empty), replacing every `require_email_access` call in `app/api/finance.py`.

- [ ] **Step 1: Write failing tests**
  - `test_active_mailbox_ids_excludes_demo` and `test_invoice_mailbox_ids_includes_demo`: compile each function's statement against the postgres dialect (as `tests/database/test_bank_connections.py` does) and assert the `provider != 'demo'` condition is present only in the first.
  - `test_finance_invoices_use_the_invoice_scope`: patch `mailboxes.invoice_mailbox_ids` to `[ID]` and `active_mailbox_ids` to `[]`; `GET /finance/invoices` still answers 200 for the owner.
  - `test_finance_turn_uses_the_invoice_scope`: the Finance agent run receives `invoice_mailbox_ids`.
  - `test_yahoo_ingest_ignores_the_demo_mailbox`: with a demo mailbox in the fake session, `upsert_yahoo_mailbox` returns the Yahoo mailbox and leaves the demo one unchanged (the email cron's only mailbox lookup).
  - Update existing Finance tests that patch `active_mailbox_ids` to patch `invoice_mailbox_ids` instead (`test_finance_invoices.py`, `test_finance_payments.py`, `test_finance_access.py`, `test_finance_turn.py`); Email tests stay as they are.

- [ ] **Step 2: Run; expect failures.**

- [ ] **Step 3: Implement** the enum value, the two functions, `require_invoice_mailboxes`, and the call-site swaps.

- [ ] **Step 4: Migration.** `uv run alembic revision --autogenerate -m "mailbox provider demo"`; autogenerate won't see the check constraint, so add by hand: `op.drop_constraint("ck_mailboxes_provider", "mailboxes", type_="check")` then `op.create_check_constraint("ck_mailboxes_provider", "mailboxes", "provider IN ('yahoo', 'gmail', 'demo')")`, and the reverse in `downgrade`. Run `uv run alembic check` only after the owner has applied it; until then, note the pending revision in the PR.

- [ ] **Step 5: Full fast suite and ruff green.**

- [ ] **Step 6: Commit** `feat(demo): demo mailbox provider, outside Email, inside Finance`

---

### Task 3: Demo bank, kept out of sync, expiry and Connect

**Files:**
- Modify: `backend/app/database/bank_connections.py` (`DEMO_BANK = "Demo Bank"`, `sync_targets`, `connection_states`, `list_connections`)
- Modify: `backend/app/api/finance.py` (`start_bank_connection`, `bank_connection_callback`)
- Create: `backend/app/demo/__init__.py`, `backend/app/demo/accounts.py`
- Modify: `frontend/src/lib/api.ts:116` (`BankName` gains `'Demo Bank'`)
- Test: `backend/tests/database/test_bank_connections.py`, `backend/tests/api/test_finance_bank_connections.py`, `backend/tests/demo/test_accounts.py` (new)

**Interfaces:**
- Consumes: `is_demo_user` (Task 1), `MailboxProvider.DEMO` (Task 2).
- Produces: `DEMO_BANK: str`; `ensure_demo_accounts(session: Session, user_id: UUID) -> DemoAccounts` where `DemoAccounts` is a frozen dataclass `(mailbox_id: UUID, account_id: UUID)`; idempotent; creates when missing: `Mailbox(provider="demo", address="demo@folio.example", display_name="Demo")`, `BankConnection(bank=DEMO_BANK, session_id="demo", valid_until=now + 10 years)`, `BankAccount(uid="demo", identification_hash="demo", iban="DE89370400440532013000", name="Girokonto", currency="EUR")`. Assumes the `users` row exists (003/03's route calls `chats.ensure_user` first). Used by 003/03, 003/04, 003/05.

- [ ] **Step 1: Write failing tests**
  - `test_sync_targets_skip_the_demo_bank` and `test_connection_states_skip_the_demo_bank`: compiled statements filter `bank IN ('N26', 'ING', 'PayPal')`.
  - `test_owner_still_syncs_all_real_banks`: with connections for N26, ING, PayPal and Demo Bank, `sync_targets` returns the three real ones.
  - `test_demo_user_lists_only_the_demo_bank`: with `demo_user_id` set and a Demo Bank connection, `list_connections(demo_id)` returns one entry `{"bank": "Demo Bank", "connected": True, "status": "active", ...}` with its account.
  - `test_owner_list_is_unchanged`: the owner gets N26, ING, PayPal in order.
  - `test_demo_user_cannot_start_a_connection`: `POST` start route → 403; the callback → 403.
  - `test_demo_user_sync_now_fetches_nothing`: with Enable Banking calls patched to fail the test if called, Sync now for the demo user returns 200 with `fetched == 0`.
  - `test_ensure_demo_accounts_is_idempotent`: on an in-memory fake session, two calls create one mailbox, one connection, one account and return the same ids.

- [ ] **Step 2: Run; expect failures.**

- [ ] **Step 3: Implement**: the `BANKS` filter in `sync_targets` and `connection_states`; in `list_connections`, `banks = (DEMO_BANK,) if is_demo_user(user_id) else BANKS`; a 403 guard at the top of both connection routes; `ensure_demo_accounts`; the `BankName` type.

- [ ] **Step 4: Backend fast suite, ruff, `pnpm exec tsc --noEmit`, `pnpm lint` green.**

- [ ] **Step 5: Commit** `feat(demo): demo bank outside sync, expiry and Connect`

---

### Task 4: Verify and record

- [ ] Every `(test)` criterion in [01-demo-user.md](01-demo-user.md) maps to a passing test; run the full fast suite once more.
- [ ] Ask the owner before applying the migration to the shared database; after applying, `uv run alembic check` is clean.
- [ ] Add a `Verified` section to the task file (date, one line per criterion, PR link); tick 003/01 in the spec only if all passed; set the spec's status to `In progress`.

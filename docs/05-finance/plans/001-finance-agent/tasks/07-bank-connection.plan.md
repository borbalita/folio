# 001/07 — Bank connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner connects N26, ING and PayPal from `/finance/accounts` through Enable Banking and sees each account with its consent expiry.

**Architecture:**
- An async Enable Banking client signs every request with an RS256 JWT and runs the consent flow:
  1. `POST /auth` returns the bank's URL.
  2. The bank redirects the browser to the frontend callback page.
  3. The callback page posts `code` and `state` to the backend.
  4. The backend exchanges the code with `POST /sessions`.
- Each bank has one `bank_connections` row. It carries a one-time `pending_state` while a connection is in flight. Accounts are stored in `bank_accounts`, keyed by Enable Banking's stable `identification_hash`.
- All routes sit on the existing owner-only `/finance` router.

**Tech Stack:** FastAPI, httpx (async), PyJWT + cryptography (new, pinned), SQLAlchemy + Alembic, React + TS.

**Spec:** [../README.md](../README.md) (Decisions, Design, Key concepts), task [07-bank-connection.md](07-bank-connection.md), API facts in [../research.md](../research.md) § Enable Banking.

## Global Constraints

- JWT: `alg` RS256, header `kid` = application id, claims `iss` `enablebanking.com`, `aud` `api.enablebanking.com`, `iat`, `exp`; lifetime at most 86400 s (use 3600).
- API base URL `https://api.enablebanking.com`. Banks are `N26`, `ING` and `PayPal`, all with country `DE` and `psu_type` `personal`. Request `access.valid_until` = now + 180 days.
- Settings in `app/config.py` only: `enable_banking_app_id`, `enable_banking_private_key` (PEM contents), `enable_banking_redirect_url`. All are optional. The API starts without them; starting a connection fails with a clear error that names the missing setting.
- Every new table enables RLS in its migration and is listed in that migration's `RLS_TABLES`.
- N26: keep only accounts with an IBAN (the main account). Spaces have no IBAN and are dropped. Other banks keep every account.
- New runtime deps `pyjwt` and `cryptography`, pinned exactly. The commit message answers the three questions in `AGENTS.md` § Dependency policy.
- The private key is never logged, returned by the API, or committed. Test keys are generated inside tests.
- JSON responses use camelCase keys, like the invoice routes.

## Review Focus

1. **The owner cancels at the bank.** The callback URL then carries `error` (and `error_description`) instead of `code`. The page shows the error and a link back to Accounts, and never calls the backend. (Task 4)
2. **A callback is replayed or arrives twice** (refresh, React StrictMode double effect). The first request completes the connection. A second one with the same `state` gets 400, because `pending_state` was cleared. The page must not show that 400 as a failure when the first one already succeeded: send the request once, guarded by a ref. (Tasks 2 and 4)
3. **Reconnecting a bank that is already connected** updates the same connection and the same account rows by `identification_hash`. It creates no duplicates and keeps account ids stable for 001/08. (Task 2)
4. **The PEM arrives as one line with literal `\n`,** as Railway variables often do. The settings validator turns `\n` into newlines. (Task 1)
5. **Enable Banking rejects the code** (`invalid_grant`, seen in research). The callback returns 502 with "Bank connection failed; start it again." and the provider's message is logged, not returned. `pending_state` is cleared, so the owner starts over. (Tasks 1 and 3)

---

### Task 1: Settings and Enable Banking client

**Files:**
- Modify: `backend/pyproject.toml` (+ `uv.lock`): `pyjwt==<latest 2.x>`, `cryptography==<latest>`, pinned exactly
- Modify: `backend/app/config.py`, `backend/.env.example`
- Create: `backend/app/finance/enable_banking.py`
- Test: `backend/tests/finance/test_enable_banking.py`

**Interfaces:**
- Produces:
  - `class EnableBankingNotConfigured(Exception)`: its message names the missing setting(s), e.g. `"Enable Banking is not configured: ENABLE_BANKING_APP_ID missing"`.
  - `class EnableBankingError(Exception)`: a non-2xx response; carries `status: int` and `body: str`.
  - `def sign_jwt(app_id: str, private_key_pem: str, now: datetime) -> str`
  - `@dataclass(frozen=True) class EbAccount`: `uid: str`, `identification_hash: str`, `iban: str | None`, `name: str | None`, `currency: str | None`
  - `@dataclass(frozen=True) class EbSession`: `session_id: str`, `valid_until: datetime`, `accounts: list[EbAccount]`
  - `async def start_authorization(bank: str, state: str, *, client: httpx.AsyncClient | None = None) -> str` returns the bank URL (`url` from `POST /auth`). Body: `{"access": {"valid_until": <now+180d ISO>}, "aspsp": {"name": bank, "country": "DE"}, "state": state, "redirect_url": settings.enable_banking_redirect_url, "psu_type": "personal"}`.
  - `async def create_session(code: str, *, client: httpx.AsyncClient | None = None) -> EbSession`: `POST /sessions` with `{"code": code}`. Parse `session_id`, `access.valid_until`, and per account `uid`, `identification_hash`, `account_id.iban`, `name`, `currency`.
  - Both raise `EnableBankingNotConfigured` before any network call when a setting is missing. Both send `Authorization: Bearer <sign_jwt(...)>`. The `client` parameter exists for tests (`httpx.MockTransport`).

- [ ] **Step 1: Write failing tests**
  - `test_jwt_header_and_claims_match_enable_banking`: generate an RSA key in the test (`cryptography`), call `sign_jwt("app-123", pem, now)`, then decode with the public key, `audience="api.enablebanking.com"` and `algorithms=["RS256"]`. Assert the header `alg == "RS256"` and `kid == "app-123"`, the claims `iss == "enablebanking.com"`, `aud == "api.enablebanking.com"`, `iat == int(now.timestamp())`, and `0 < exp - iat <= 86400`.
  - `test_private_key_with_literal_newlines_is_normalised`: settings built with the PEM's newlines replaced by `\\n` produce a key that `sign_jwt` accepts.
  - `test_start_authorization_without_app_id_names_the_setting`: with `enable_banking_app_id=None`, raises `EnableBankingNotConfigured`, the message contains `ENABLE_BANKING_APP_ID`, and the mock transport received no request.
  - `test_start_authorization_sends_bank_state_and_redirect`: the mock transport asserts the body above (`aspsp.name == "N26"`, `country == "DE"`, `state`, `redirect_url`, `psu_type == "personal"`, `valid_until` 180 days ahead ± 1 minute) and the bearer header. It returns `{"url": "https://bank.example/x"}`, and the result is that URL.
  - `test_create_session_parses_accounts`: a mocked `POST /sessions` response with two accounts, one with `account_id.iban` and one without. Assert the `EbSession` fields.
  - `test_error_response_raises_enable_banking_error`: the mock returns 400 `{"error": "invalid_grant"}`, so `EnableBankingError` is raised with `status == 400`.
- [ ] **Step 2:** `cd backend && uv run pytest tests/finance/test_enable_banking.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.**
  - Settings: three `str | None = None` fields, added to the existing `blank_optional_str` validator. Add a validator on `enable_banking_private_key` that replaces literal `\n` with newlines.
  - Client: the base URL is a module constant, the timeout 30 s, and `raise_for_status` is mapped to `EnableBankingError`.
- [ ] **Step 4:** Run the same tests. Expected: PASS. Then `uv run pytest -m "not integration"` and `uv run ruff check .` pass.
- [ ] **Step 5: Commit**: `feat(finance): Enable Banking client with signed requests (001/07)`, with the dependency answers in the body.

### Task 2: Connection and account storage

**Files:**
- Create: `backend/app/database/models/finance/__init__.py`, `bank_connection.py`, `bank_account.py`; register both in `backend/app/database/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_bank_connections_and_accounts.py` (autogenerate, then add the RLS block and `RLS_TABLES = ("bank_connections", "bank_accounts")`, following `ec52ad5d7695`)
- Create: `backend/app/database/bank_connections.py`
- Test: `backend/tests/database/test_bank_connections.py`

**Interfaces:**
- Consumes: `EbSession`, `EbAccount` (Task 1).
- Produces:
  - Table `bank_connections`: `id` uuid pk; `user_id` FK `users.id` cascade; `bank` str(32); `session_id` text null; `valid_until` timestamptz null; `pending_state` text null, unique; `created_at`; `updated_at`. Unique `(user_id, bank)`.
  - Table `bank_accounts`: `id` uuid pk; `connection_id` FK cascade; `uid` text; `identification_hash` text; `iban` text null; `name` text null; `currency` str(3) null; `created_at`. Unique `(connection_id, identification_hash)`.
  - `BANKS: tuple[str, ...] = ("N26", "ING", "PayPal")`
  - `def keep_accounts(bank: str, accounts: list[EbAccount]) -> list[EbAccount]`: drops IBAN-less accounts for `N26` only.
  - `def begin_connection(user_id: uuid.UUID, bank: str, state: str) -> None`: upserts the `(user_id, bank)` row and sets `pending_state`. An active `session_id` stays untouched.
  - `def find_pending(user_id: uuid.UUID, state: str) -> str | None`: the bank name for this user's pending state, or `None`.
  - `def complete_connection(user_id: uuid.UUID, state: str, session: EbSession) -> None`: finds the row by `(user_id, pending_state=state)`, sets `session_id` and `valid_until`, clears `pending_state`, and upserts `keep_accounts(...)` by `identification_hash` (updating `uid`, `iban`, `name`, `currency`). Raises `UnknownState` (defined here) when there is no row.
  - `def clear_pending(user_id: uuid.UUID, state: str) -> None`
  - `def list_connections(user_id: uuid.UUID) -> list[dict[str, Any]]`: one entry per bank in `BANKS` order, `{"bank", "connected": bool, "validUntil": iso | None, "accounts": [{"id", "name", "ibanMasked", "currency"}]}`. `ibanMasked` keeps the first 4 and last 4 characters, for example `"DE89 •••• 3000"`, and is `None` without an IBAN.

- [ ] **Step 1: Write failing tests** (unit tests for the pure functions; database helpers follow the existing `tests/database` patterns):
  - `test_n26_keeps_only_the_main_account`: N26 with one IBAN account and three without, so only the IBAN account is kept.
  - `test_other_banks_keep_accounts_without_iban`: PayPal with one IBAN-less account keeps it.
  - `test_complete_connection_with_unknown_state_raises`: raises `UnknownState`.
  - `test_account_upsert_conflicts_on_identification_hash`: the account upsert statement, built by `def account_upsert(connection_id: uuid.UUID, accounts: list[EbAccount])` and compiled with the postgresql dialect, contains `ON CONFLICT (connection_id, identification_hash) DO UPDATE` and updates `uid`, `iban`, `name` and `currency`. Database tests here mock the session (see `tests/database/test_chats.py`), so the no-duplicates behaviour itself is checked by hand with Reconnect.
  - `test_mask_iban`: `"DE89370400440532013000"` → `"DE89 •••• 3000"`.
  - `test_list_connections_lists_all_banks_in_order`: an unconnected bank shows `connected: False`, `validUntil: None` and `accounts: []`.
- [ ] **Step 2:** `uv run pytest tests/database/test_bank_connections.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Write the models, then `uv run alembic revision --autogenerate -m "add bank connections and accounts"` and add the RLS block by hand. **Do not run `alembic upgrade`**: the controller applies the migration with the owner's permission. Then the helpers.
- [ ] **Step 4:** Run the tests above, plus `tests/database/test_rls_migration.py`, and `uv run alembic heads` (single head). Expected: PASS, one head.
- [ ] **Step 5: Commit**: `feat(finance): bank connections and accounts tables (001/07)`.

### Task 3: Finance bank-connection routes

**Files:**
- Modify: `backend/app/api/finance.py`
- Test: `backend/tests/api/test_finance_bank_connections.py`

**Interfaces:**
- Consumes: Task 1 client and errors; Task 2 helpers and `UnknownState`; router-level owner check (existing).
- Produces:
  - `GET /finance/bank-connections` returns `list_connections(user.id)`.
  - `POST /finance/bank-connections/{bank}/start`: 404 when `bank` is not in `BANKS`. Generates the state with `secrets.token_urlsafe(32)`, calls `begin_connection`, then `start_authorization`, and returns `{"url": ...}`. `EnableBankingNotConfigured` gives 503 with its message. `EnableBankingError` gives 502 `"Could not reach the bank; try again."`, with the body logged.
  - `POST /finance/bank-connections/callback` with body `{"code": str, "state": str}`:
    - Unknown state: 400 `"Unknown or expired connection attempt."`, checked with `find_pending` **before** any Enable Banking call.
    - Otherwise `create_session`, then `complete_connection`, and returns `list_connections(user.id)`.
    - On `EnableBankingError`: `clear_pending`, then 502 `"Bank connection failed; start it again."`

- [ ] **Step 1: Write failing tests**, monkeypatching the client functions and database helpers at the `app.api.finance` boundary, as `test_finance_invoices.py` does:
  - `test_callback_with_wrong_state_is_refused`: `find_pending` returns `None`, so the response is 400 and `create_session` is not called.
  - `test_callback_completes_connection`: a known state calls `create_session(code)` and `complete_connection(...)`, and returns 200 with the list.
  - `test_callback_bank_error_clears_pending`: `create_session` raises `EnableBankingError`, so the response is 502 and `clear_pending` is called.
  - `test_start_unknown_bank_is_404`.
  - `test_start_without_config_is_503_naming_setting`: the response body contains `ENABLE_BANKING`.
  - `test_non_owner_gets_403_on_bank_connection_routes`: follows the existing owner-check pattern in `test_finance_access.py`.
- [ ] **Step 2:** `uv run pytest tests/api/test_finance_bank_connections.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement the routes.** Run the blocking database helpers with `asyncio.to_thread`, as the invoice routes do.
- [ ] **Step 4:** The tests above pass, as do the full `uv run pytest -m "not integration"` and `ruff`.
- [ ] **Step 5: Commit**: `feat(finance): bank connection routes (001/07)`.

### Task 4: Accounts page and callback page

**Files:**
- Modify: `frontend/src/lib/api.ts` (types `BankConnection`, `BankAccount`; `listBankConnections`, `startBankConnection(bank)`, `completeBankConnection(code, state)`)
- Modify: `frontend/src/pages/finance/AccountsPage.tsx`
- Create: `frontend/src/pages/finance/BankCallbackPage.tsx`
- Modify: `frontend/src/App.tsx`: route `accounts/callback` under `/finance`
- Modify: `frontend/.env.example` only if a new variable is needed (none expected)

**Interfaces:**
- Consumes: the Task 3 routes and response shapes.
- Behaviour:
  - **AccountsPage:** one card per bank in API order.
    - Not connected: a "Connect" button, which calls `startBankConnection` and sets `window.location.href = url`.
    - Connected: "Valid until <date>" (use `lib/format.ts` if it has a date formatter), the accounts as `name · ibanMasked · currency`, and a "Reconnect" button.
    - Loading and error states follow `InvoicesPage.tsx`. A 503 shows the server message.
  - **BankCallbackPage** (`/finance/accounts/callback`):
    - With `error` in the query, it shows `error_description ?? error` and a link to Accounts, with no API call.
    - With `code` and `state`, it calls `completeBankConnection` **once** (a `useRef` guard against the StrictMode double effect), then `navigate('/finance/accounts', { replace: true })`.
    - If the call fails, it shows the error and a link back.

- [ ] **Step 1: Implement** the API client, both pages and the route.
- [ ] **Step 2:** `cd frontend && pnpm tsc --noEmit && pnpm lint`. Expected: both clean.
- [ ] **Step 3: Commit**: `feat(finance): accounts page with bank connect flow (001/07)`.

### Controller steps (main session, with the owner)

- Apply the migration (`uv run alembic upgrade head`), with the owner's permission.
- The owner adds the three Enable Banking settings to `backend/.env`. The controller never reads them.
- Register the redirect URLs in the Enable Banking control panel (owner): `http://localhost:5173/finance/accounts/callback` and the deployed frontend's `/finance/accounts/callback`. Record in the spec whether plain-http localhost is accepted. If it isn't, try `https://localhost` with Vite's `--https`, or use the deployed URL.
- Manual acceptance: connect N26, ING and PayPal. All three show their accounts and expiry, with N26 showing only the main account.
- Review Focus 3 by hand: click Reconnect on one bank. Its account count stays the same, and the account ids from `GET /finance/bank-connections` don't change.

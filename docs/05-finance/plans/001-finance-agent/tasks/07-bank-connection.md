# 001/07 — Connect bank accounts through Enable Banking

## Goal
The owner connects N26, ING and PayPal from the Finance accounts page and sees each account with its consent expiry.

## Scope
- Settings: Enable Banking app id, private key (PEM contents), redirect URL. The API starts without them; connecting fails with a clear error when one is missing.
- A client that signs requests (RS256 JWT, `kid` = app id) and runs the consent flow: start, bank redirect, callback with `state` check, session.
- Bank connections and accounts tables, with RLS; the N26 main account is kept and N26 Spaces are left out.
- Accounts page: connect per bank, list of accounts with masked IBAN and `valid_until`.
- Register the redirect URLs (deployed frontend, and http localhost if Enable Banking accepts it).

## Out of scope
- Transactions (001/08); expiry handling (001/11).

## Acceptance criteria
- Given the key and app id, when a request is signed, then the JWT header and claims match Enable Banking's format. (test)
- Given a callback with a wrong `state`, when it arrives, then it is refused. (test)
- Given an N26 session with a main account and Spaces, when it is stored, then only the main account is kept. (test)
- Given the owner, when N26, ING and PayPal are connected from the accounts page, then all three accounts show with their expiry. (manual)

## Dependencies
001/03.

## Notes
- Most uncertain task: whether the localhost redirect must be https. Record the answer in the spec.
- Secrets: the private key only on the laptop and in Railway's variables.
- Implementation plan: [07-bank-connection.plan.md](07-bank-connection.plan.md).

## Verified

2026-10-09, branch `feat/finance-bank-connection`.

- JWT header and claims match Enable Banking's format: `test_jwt_header_and_claims_match_enable_banking`. Pass.
- A callback with a wrong `state` is refused: `test_callback_with_wrong_state_is_refused`, `test_complete_connection_with_unknown_state_raises`. Pass.
- N26 with a main account and Spaces keeps only the main account: `test_n26_keeps_only_the_main_account`. Pass.
- N26, ING and PayPal connected from the accounts page show with their expiry (manual): the owner connected all three from `https://localhost:5173/finance/accounts`. The database holds one account per bank: N26 main (IBAN, no Spaces), ING (IBAN) and PayPal (no IBAN). Each has a session and consent valid until 2027-04-07 (180 days). The owner confirmed the page shows all three with their expiry. Pass.
- Suite: `uv run pytest -m "not integration"`: 218 passed. `ruff check` is clean. `pnpm tsc --noEmit` and `pnpm lint` are clean.

Found during verification:
- Enable Banking accepts only https redirect URLs, localhost included. Saving `http://localhost:…` fails with "unsupported scheme", and a redirect URL not registered on the application gives `REDIRECT_URI_NOT_ALLOWED`. Local work now runs the Vite dev server on https with a self-signed certificate (`daf4d82`). This is recorded in the spec.
- A configuration error from Enable Banking (any 4xx on `POST /auth`) is reported as 502 "Could not reach the bank". The frontend then shows the chat's generic "The assistant couldn't complete this answer." Fixed in this branch (see the next commit).

PR: pending.

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

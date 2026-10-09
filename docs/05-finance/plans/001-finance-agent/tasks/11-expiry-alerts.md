# 001/11 — Consent expiry alerts and Reconnect all

## Goal
The owner is warned before bank access expires and renews all connections in one sitting.

## Scope
- Connection status: active, expiring (14 days before `valid_until`), expired (after it, or when the API reports an invalid session). The scheduled sync skips expired connections and keeps syncing the rest.
- Warning in Finance; emails from the bank sync at 14 days, 3 days and on expiry, once each, through Yahoo SMTP with the existing app password (stdlib `smtplib`), linking to the accounts page.
- Reconnect all: the consent flow for each expiring or expired bank in turn; accounts matched by provider id or IBAN, so history stays.

## Out of scope
- Other notification channels.

## Acceptance criteria
- Given a connection 13 days from expiry, when sync runs, then it is expiring and one email is sent; a second run sends none. (test)
- Given an invalid-session answer, when sync runs, then the connection is expired and the other accounts still sync. (test)
- Given a reconnected bank, when its accounts come back, then existing transactions stay linked to them. (test)
- Given expiring connections, when the owner uses Reconnect all, then each bank's approval runs in turn and all show active. (manual)

## Dependencies
001/08.

# 001/08 — Transactions sync from all connected accounts

## Goal
Booked transactions from the N26 main account, ING and PayPal are stored without duplicates, three times a day and on demand.

## Scope
- A transactions table with RLS (date, signed amount, currency, counterparty name and IBAN, remittance text, bank code, raw entry).
- A sync command: paginated fetch since the last booking date minus 7 days, booked entries only, PayPal's transaction date used as booking date.
- Deduplication by the bank's `entry_reference` together with direction where present, otherwise by date, amount, counterparty, text and an ordinal within the day.
- Sync now on the accounts page (refused within 10 minutes of the previous sync); each run in the job-run log.
- A plain transactions list in Finance (date, account, counterparty, amount).
- A Railway cron service for the bank sync, three times a day.

## Out of scope
- Matching (001/09); expiry alerts (001/11).

## Acceptance criteria
- Given two pages from the API, when sync runs, then both pages are stored. (test)
- Given pending entries, when sync runs, then they are not stored. (test)
- Given the overlap window, when sync runs twice, then no transaction is stored twice. (test)
- Given two identical N26 rows on one day, when sync runs, then both are stored. (test)
- Given a debit and its refund sharing an `entry_reference`, when sync runs, then both are stored. (test)
- Given the connected accounts, when the cron has run, then 90 days of transactions show and a second run adds nothing. (manual)

## Dependencies
001/07; 001/02 for the job-run log.

## Notes
- Real-data findings in [research.md](../research.md#real-data-check-2026-10-08).

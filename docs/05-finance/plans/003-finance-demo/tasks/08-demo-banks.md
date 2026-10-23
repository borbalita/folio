# 003/08 — Three demo accounts, including a wallet

## Goal
The demo shows money in several places, as in real life: two bank accounts and a PayPal-like wallet, and an invoice paid from the wallet is still matched automatically.

## Scope
- Replace the one "Demo Bank" connection with three fictional ones: **Spreeufer Bank** (account "Girokonto", the main account: salary, rent, invoice debits and the presenter's bookings), **Kiez Direkt** (account "Alltagskonto": card payments) and **TalerPay** (a wallet without an IBAN, like a PayPal account).
- Base state (003/03): transactions spread over the three; one of the "matched automatically" invoices is paid from TalerPay and matched by the invoice number in the payment text.
- Reset also deletes the demo user's other connections (the old "Demo Bank").
- The demo user's Accounts page lists the three; Connect stays refused for them. The frontend no longer compares bank names: the API says whether a connection can be connected.
- Sync and expiry checks keep covering only the real banks (N26, ING, PayPal).

## Out of scope
- Real bank names for demo data (rejected: they could be mistaken for real accounts, and the code treats those names as live connections).

## Acceptance criteria
- Given a reset, then the demo user has exactly the three demo connections, each with transactions, and no "Demo Bank". (test)
- Given a reset, then one invoice is paid and matched automatically by a TalerPay transaction. (test)
- Given a booking from the presenter page, then the debit lands in Spreeufer Bank's Girokonto. (test)
- Given the demo user, when the Accounts and Transactions pages open, then three accounts show without a Connect button, and the transactions name their account. (browser)

## Dependencies
003/03, 003/05. Before 003/07 (the rehearsal and the video).

## Notes
- Decided in chat 2026-10-22, added to the plan 2026-10-23, for the presentation video: fictional names in the style of the demo vendors; the voice-over can say "in my own setup these are N26, ING and PayPal".

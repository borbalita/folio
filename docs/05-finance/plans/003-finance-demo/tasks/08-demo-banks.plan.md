# 003/08 — Three demo accounts: implementation plan

Task: [08-demo-banks.md](08-demo-banks.md).

- `bank_connections.py`: `DEMO_BANK` becomes `DEMO_BANKS = ("Spreeufer Bank", "Kiez Direkt", "TalerPay")`; the demo user's list shows those three. Every entry gets `connectable: bank in BANKS`, so the frontend stops comparing names. Sync targets and expiry states keep filtering on `BANKS`.
- `demo/accounts.py`: one connection and one account per demo bank: Spreeufer Bank "Girokonto" (`DE89370400440532013000`, as before), Kiez Direkt "Alltagskonto" (a demo IBAN), TalerPay "TalerPay-Konto" (no IBAN). `DemoAccounts` keeps `account_id` (the Girokonto, used by bookings) and adds `card_account_id`, `wallet_account_id` and `account_ids`.
- `demo/reset.py`: deletes the transactions of all three accounts and the demo user's connections that aren't demo banks (the old "Demo Bank", with its account and transactions by cascade).
- `demo/base_state.py`: the ledger writes to a given account. Salary, rent, transfers and the prepaid debit stay on the Girokonto; card payments go to Kiez Direkt; a few online purchases and the Zahnarzt invoice's payment go to TalerPay (counterparty "TalerPay *…", invoice number in the text, no IBAN; match signals amount + reference).
- Frontend: `BankName` widens to a string; `BankConnection` gains `connectable`; Accounts hides Connect when it is false.
- Tests: accounts (three connections, TalerPay without IBAN, `account_id` is the Girokonto), base state (every account has transactions; one matched invoice is paid from TalerPay by reference), reset (all three accounts' transactions and non-demo connections deleted), bank connections (demo user lists the three, not connectable; owner unchanged, connectable).

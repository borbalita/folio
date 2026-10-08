# 001 — Research notes

Reference material from Stage 2 (2026-10-06). The spec ([README.md](README.md)) holds the current decisions.

## Enable Banking

- Enable Banking's public directory (`https://enablebanking.com/api/aspsps`, fetched 2026-10-06) lists for country DE:

  | Name | BIC | PSU types | Max consent | Beta |
  |---|---|---|---|---|
  | N26 | NTSBDEBBXXX | personal, business | 180 days | no |
  | ING | INGDDEFFXXX | personal, business | 180 days | no |
  | PayPal | — | personal, business | 180 days | no |

  PayPal with a personal account is supported, so plan 002 does not need a PayPal Business account or the PayPal API.
- API reference: <https://enablebanking.com/docs/api/reference/>
  - JWT: `alg` RS256, header `kid` = application id, claims `iss` `enablebanking.com`, `aud` `api.enablebanking.com`, `iat`, `exp`; lifetime at most 86400 s.
  - `POST /auth`: `access.valid_until`, `aspsp` (name, country), `state`, `redirect_url`, `psu_type`.
  - `POST /sessions`: returns `session_id`, `accounts`, `access.valid_until`.
  - `GET /accounts/{account_id}/transactions`: `date_from`, `date_to`, `continuation_key`, `transaction_status`, `strategy`.
  - Transaction fields: `entry_reference`, `transaction_id`, `transaction_amount`, `credit_debit_indicator`, `creditor`, `debtor`, `creditor_account`, `remittance_information`, `booking_date`, `value_date`, `status`, `merchant_category_code`, `bank_transaction_code`.
  - `POST /payments`: `payment_type`, `payment_request`, `aspsp`, `redirect_url`, `psu_type`, optional `defer_submission`.
- Restricted mode, as described by integrators: accounts must first be linked in the Enable Banking control panel; the app then sees only those. [Firefly III guide](https://docs.firefly-iii.org/tutorials/data-importer/eb/), [Actual Budget guide](https://actualbudget.org/docs/advanced/bank-sync/enable-banking).
- GoCardless Bank Account Data (Nordigen) closed to new signups in July 2025: <https://bankaccountdata.gocardless.com/new-signups-disabled>.

## PSD2 limits

- Unattended access (no user present): up to 4 times per 24 hours per account, under the PSD2 regulatory technical standards on strong customer authentication. User-initiated requests are not limited this way.

## EPC QR code (GiroCode)

- N26 scans EPC QR codes on Android and iOS and imports them from photos: [mobiflip](https://www.mobiflip.de/shortnews/n26-neue-funktionen-per-update-epc-qr-code-scanner-fuer-android-und-mehr/).
- ING Banking to go: photo transfer reads invoices and QR codes into a transfer: [ING](https://www.ing.de/wissen/banking-to-go/).

## Railway cron

- <https://docs.railway.com/reference/cron-jobs>: UTC schedules, at least 5 minutes apart; a run is skipped while the previous one is `Active`; the service must exit when its task is done.

## Real data check (2026-10-08)

A throwaway script outside the repo pulled 90 days from the user's own accounts through Enable Banking (7-day consent). Raw data stays in `~/.config/folio/eb-spike/`; only counts were read.

| Account | Transactions | Notes |
|---|---|---|
| N26 main account | 421 (391 debits) | 339 card payments, 36 direct debits, 23 transfers |
| N26 Spaces (9) | 0–1 each | Spaces have no IBAN; no Space movements visible in the main account |
| ING | 64 (50 debits, 3 pending) | 37 direct debits, 8 transfers, 4 fees |
| PayPal | 48 (45 debits) | merchant as creditor name, no reference text |

- **Ids are unreliable.** No account fills `transaction_id`. N26 fills `entry_reference` on 175 of 421 rows, and never on transfers; one value is shared by a debit and its later refund. ING and PayPal fill `entry_reference` on every row. Deduplication needs a fallback key, and that key needs an ordinal: two N26 rows share date, amount, name and text.
- **Transfers carry what invoice matching needs.** All 40 N26 debits with a counterparty IBAN also have remittance text; ING transfers have an IBAN and long remittance text (47 of 64 rows contain an invoice-like token). Card payments have neither an IBAN nor text.
- **Direct debits have no counterparty IBAN** on either bank, only name and text.
- **No merchant category codes** anywhere. Categorization (plan 002) has merchant name and text only.
- **PayPal linking works on amount and date.** 31 of 32 N26 debits to PayPal match exactly one PayPal debit with the same amount 0–5 days earlier; one has none. 14 PayPal debits are not funded from N26 (balance or another source).
- **PayPal has only `transaction_date`** (no booking or value date).
- **ING reports pending entries dated in the future** (3 scheduled payments). Only booked entries should be stored.
- **Consent:** each bank needs its own approval; one ING attempt returned `invalid_grant` and a fresh link worked.

## Payment initiation test (2026-10-08)

- A €0.01 transfer from the N26 main account to the user's own ING account was prepared by a throwaway script and confirmed by the user in the terminal. `POST /payments` returned `403 ACCESS_DENIED` ("Check services available for your application"). `GET /application` lists `services: ["AIS"]` only. No payment was created.

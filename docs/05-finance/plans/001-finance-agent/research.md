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

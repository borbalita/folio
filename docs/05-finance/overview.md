# Finance agent — overview

What the Finance agent does today and why it works the way it does. The design and its decisions are in [plan 001](plans/001-finance-agent/README.md).

## What it is

The third card on the agent picker, for one owner only (`FINANCE_OWNER_USER_ID`). It tracks the invoices that arrive by email, reads the owner's bank and PayPal transactions, marks invoices paid when the money has left, and prepares payments that the owner pays by scanning a QR code in their banking app. It has pages for Invoices, Chat, Transactions and Accounts.

## Invoices from email

Email ingest (Railway cron, every 30 minutes) labels each email ([email overview](../03-email/overview.md)). For invoice mail:

1. **Detect.** A cheap check (`gpt-6-luna`, `invoice_check_model`) reads the email and its PDFs and gives one verdict:

   | Verdict | In Finance |
   |---|---|
   | `to_pay` | extracted: `open`, or `needs_info` when data is missing |
   | `already_paid` (paid online, "amount received") | extracted and recorded as paid (`paid_by = "invoice"`), shown as "Paid before it arrived" |
   | `online_only` ("your bill is ready online") | `needs_info`: download it, or check whether it must be paid; no extraction call |
   | `none` | `needs_info` "no invoice found" for invoice mail; nothing for other mail |

   A PDF named like an invoice (`rechnung`, `invoice`, `faktura`, `számla` …) labels the email `invoice` without the classifier. Other mail with a PDF becomes an invoice only on a clear `to_pay` or `already_paid`.
2. **Extract.** One structured call (`gpt-6.1-sol`, `INVOICE_EXTRACTION_MODEL`) gets the PDFs as files, so scans work, and returns one or more invoices per email: payee, IBAN, BIC, amount, currency, invoice number, reference, invoice and due dates. The payee is the account holder named with the bank details, because the QR code carries that name and the bank checks it against the IBAN.
3. **Check.** IBAN length and mod-97, amount above zero, currency EUR. A failure makes the invoice `needs_info` with the reasons in `issues`. A failed call is retried once, then stored as `needs_info`.

Statuses: `open`, `needs_info`, `paid`. The owner edits any field on the invoice page, next to the PDF; edits are re-checked, and re-extraction never overwrites them. `python -m ingest.email.backfill_invoices` (`--detect`, `--all`) runs detection or extraction over mail already stored.

The Invoices list shows open and needs-info invoices by default, overdue first, with filters for status, dates and payee.

## Bank and PayPal transactions

- **Access.** Enable Banking holds the PSD2 licence; Folio is its client in restricted mode (free, reading only, the accounts linked in its control panel). The owner connects N26 (main account only; Spaces have no IBAN), ING and PayPal on the Accounts page. Each consent lasts 180 days and needs the owner at the bank to renew.
- **Sync.** The `bank-sync` cron (04:00, 11:00, 18:00 UTC) and Sync now fetch booked transactions from 7 days before the latest stored one (90 days on the first sync). Pending entries are skipped; PayPal's transaction date counts as the booking date.
- **Duplicates.** A transaction keeps the bank's `entry_reference` with its direction when present, otherwise a hash of date, amount, counterparty and text plus an ordinal among identical rows, so a repeat sync never stores a row twice.
- **Limits.** About four unattended reads per account a day; Sync now tells the bank the owner is present and is refused within 10 minutes of the last sync. An unreadable entry is skipped and counted, not fatal.

## Matching

After each ingest, sync and invoice edit, open invoices are compared with debits from the invoice date to 120 days later:

- **Linked** (automatic, invoice turns paid): equal amount, and equal IBAN or the invoice's number or reference in the remittance text.
- **Suggested**: equal amount and a shared payee-name token of 4+ characters, or more than one strong candidate.

Automatic links are labelled and undone in one click; suggestions have Confirm and Reject. Only a match or the owner marks an invoice paid.

## Paying

From the invoice page (Pay) or the list (Pay selected), Folio prepares a payment draft: a frozen copy of payee, IBAN, BIC, amount and reference (the invoice's reference, or its number when it asks for none). The payment card sits beside the invoice PDF, amount first. The card's fields are editable, so the owner can correct a misread value against the PDF. Pressing **Approve** is the owner's confirmation that the card matches the invoice; it saves any corrections to the invoice as owner edits (and re-runs matching), re-checks the invoice (still open, valid IBAN, same amount) and shows an EPC (GiroCode) QR code. The banking app that scans it pays from its own account: Folio names no paying account.

An invoice with an approved payment is never given a second one, so preparing again can't lead to paying twice. A draft completes when matching links its invoice. Folio cannot send payments itself: Enable Banking only grants reading (`AIS`).

## Chat

Finance → Chat answers questions about invoices, transactions and accounts with cards: invoice cards (the list component, with Pay selected) and payment cards (the Payments page's card, approved by the owner). The agent's five tools list invoices, get one, search transactions, list accounts and prepare payments; none can approve, pay or edit. Card ids must come from a tool in the same turn; others are dropped and logged. Cards load current data, so an old answer shows today's state.

## Consent expiry

Each connection is active, expiring (14 days or less) or expired (past its date, or Enable Banking reports the session gone). The bank sync skips expired connections and keeps syncing the rest. A warning shows in Finance, and emails go out at 14 days, 3 days and on expiry, once each, through Yahoo SMTP. Reconnect all runs each expiring or expired bank's approval in turn; accounts are matched by Enable Banking's id, then IBAN, so history stays.

## Access, privacy and configuration

- **Owner only.** Every Finance route returns 403 to anyone but `FINANCE_OWNER_USER_ID`; with the setting unset, Finance is off for everyone. Every table has RLS with no policies; the backend uses the service role.
- **Tracing.** Finance agent and extraction traces in Langfuse are content-free: models, tools, tokens, timings and errors only.
- **Secrets.** The Enable Banking private key lives only on the owner's laptop and in Railway's variables.
- **Settings.** `ENABLE_BANKING_APP_ID`, `ENABLE_BANKING_PRIVATE_KEY`, `ENABLE_BANKING_REDIRECT_URL`, `FINANCE_OWNER_USER_ID`, plus the model settings. Enable Banking only redirects to https, so local work runs the frontend on https with a self-signed certificate.
- **Telegram** messages about new invoices and big news are in [06-notifications](../06-notifications/overview.md).

## Not built here (plan 002)

Linking PayPal payments to the bank debits that fund them, transfers between own accounts, N26 Spaces, categories and spending.

## Known gaps

- No automatic match has happened on real data yet: every paid invoice so far was paid before it arrived or marked by the owner.
- A QR payment is only confirmed once the debit reaches a connected account.

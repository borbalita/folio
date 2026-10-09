# Privacy

Last updated: 2026-10-09

Borbfolio is a personal project with a single user: its owner. It is not offered to anyone else, and no other person's data is collected.

## What it reads

- **Bank data**, through [Enable Banking](https://enablebanking.com): the account details (name, IBAN, currency, balance) and transactions of the owner's N26, ING and PayPal accounts. The app never sees bank logins; the owner signs in on the bank's own page.
- **Invoice emails** from the owner's mailbox, including their PDF attachments, to find payee, IBAN, amount and reference.

## Where it is stored

In the app's Supabase database, readable only by the owner's account.

## Who else sees it

- Nobody. The data is never shared or sold.
- It is never sent to tracing or analytics services. Traces keep only model names, tools, token counts, timings and errors.
- The services the app runs on handle it only to do their job: Enable Banking passes bank data from the bank, Supabase and Railway store and run the app, and OpenAI reads an invoice to extract its payment data.

## Consent

Bank access lasts at most 180 days and then ends unless the owner renews it at the bank. The owner can revoke it at any time, at the bank or in the app.

## Contact

borbala@tasnadi-ai.de

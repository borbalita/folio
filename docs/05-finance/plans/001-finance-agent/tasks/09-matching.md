# 001/09 — Invoices matched to transactions

## Goal
Open invoices are linked to the debits that paid them, automatically when the match is strong and as a suggestion otherwise.

## Scope
- A matches table with RLS (invoice, transaction, linked / suggested / rejected, automatic or by the owner, which signals matched).
- Candidates: debits on or after the invoice date, up to 120 days later. Strong: equal amount and (equal IBAN or the invoice's number or reference in the remittance text) → linked and paid. Weaker: equal amount and a shared payee-name token of 4+ characters → suggestion. More than one strong candidate → all become suggestions.
- Runs after email ingest, bank sync, and an edit of invoice fields.
- UI: automatic links labelled; suggestions with Confirm and Reject; undo returns the invoice to open.

## Out of scope
- Payments (001/10).

## Acceptance criteria
- Given a debit with the invoice's amount and IBAN, when matching runs, then the invoice is paid and the link is marked automatic. (test)
- Given a debit with the amount and the invoice number in its text, when matching runs, then the invoice is paid. (test)
- Given a debit with the amount and a similar payee name only, when matching runs, then a suggestion appears and the invoice stays open. (test)
- Given two strong candidates, when matching runs, then both are suggestions. (test)
- Given a rejected suggestion, when matching reruns, then it is not suggested again. (test)
- Given an automatic link, when the owner undoes it, then the invoice is open again. (browser)
- Given the last 90 days, when the owner spot-checks, then every invoice is matched, suggested, or genuinely open. (manual)

## Dependencies
001/06, 001/08.

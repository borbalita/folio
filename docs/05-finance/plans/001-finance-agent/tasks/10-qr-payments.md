# 001/10 — Pay invoices with a GiroCode QR

## Goal
The owner selects open invoices, picks an account, checks each payment against its invoice, and pays it by scanning a QR code in the bank app.

## Scope
- Payment drafts table with RLS: a frozen copy of payee, IBAN, BIC, amount, reference, from-account; at most one open draft per invoice.
- Pay selected on the invoice list (open invoices only) with the account choice; skipped invoices listed with the reason.
- Payment card beside the invoice PDF: amount most prominent; Approve enabled only after the owner ticks that payee, IBAN, amount and reference match the invoice.
- Approve re-checks the invoice (still open, valid IBAN, same amount), then shows an EPC QR code (EPC069-12, rendered with `segno`) and copy buttons. Batches step through cards one by one.
- An approved draft completes when matching links its invoice.

## Out of scope
- Payment initiation through a bank API.

## Acceptance criteria
- Given an invoice, when the EPC payload is built, then its lines, truncation and amount format follow EPC069-12. (test)
- Given an open draft for an invoice, when another is created, then the old one is replaced. (test)
- Given an invoice paid in the meantime, when Approve is pressed, then it is refused. (test)
- Given a payment card, when the box is unticked, then Approve is disabled; when ticked, the QR shows. (browser)
- Given a real invoice, when the owner scans the QR in the N26 app and confirms, then the invoice is paid after the next sync. (manual)

## Dependencies
001/09.

## Notes
- Decision: QR now; payment initiation only if Enable Banking enables `PIS`.

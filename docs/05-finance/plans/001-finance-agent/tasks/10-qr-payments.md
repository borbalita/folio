# 001/10 — Pay invoices with a GiroCode QR

## Goal
The owner selects open invoices, checks each payment against its invoice, and pays it by scanning a QR code in the banking app.

## Scope
- Payment drafts table with RLS: a frozen copy of payee, IBAN, BIC, amount, reference; at most one open draft per invoice. The paying account is left empty: the QR code names none, and the scanning app pays from its own account (owner, 2026-10-16); the column stays for payment initiation.
- The draft's reference is the invoice's requested reference, or its invoice number when it has none (owner's choice, 2026-10-15; extraction keeps `reference` to what the invoice asks for).
- Pay selected on the invoice list (open invoices only), and Pay on the invoice page.
- Payment card beside the invoice PDF: amount most prominent; pressing Approve confirms that payee, IBAN, amount and reference match the invoice (no separate tick, owner's choice, 2026-10-16).
- Approve re-checks the invoice (still open, valid IBAN, same amount), then shows an EPC QR code (EPC069-12, rendered with `segno`) and copy buttons. Batches step through cards one by one.
- An approved draft completes when matching links its invoice.

## Out of scope
- Payment initiation through a bank API.

## Acceptance criteria
- Given an invoice, when the EPC payload is built, then its lines, truncation and amount format follow EPC069-12. (test)
- Given an open draft for an invoice, when another is created, then the old one is replaced. (test)
- Given an invoice paid in the meantime, when Approve is pressed, then it is refused. (test)
- Given a payment card, when Approve is pressed, then the QR code and copy buttons show. (browser)
- Given a real invoice, when the owner scans the QR in the N26 app and confirms, then the invoice is paid after the next sync. (manual)

## Dependencies
001/09.

## Notes
- Implementation plan: [10-qr-payments.plan.md](10-qr-payments.plan.md).
- Decision: QR now; payment initiation only if Enable Banking enables `PIS`.

## Verified

2026-10-16, PR https://github.com/borbalita/folio/pull/33, local app against the real database.

- EPC payload lines, truncation and amount format: `tests/finance/test_epc.py`. Pass.
- A new draft replaces the invoice's open one: `test_a_new_draft_replaces_the_invoices_open_one`. Pass.
- Approve refused for an invoice paid in the meantime: `test_approve_is_refused_when_the_invoice_was_paid_meanwhile`, `test_approve_is_refused_for_an_invoice_paid_in_the_meantime`. Pass.
- Approve shows the QR code and copy buttons (browser): the owner prepared a payment for a real open invoice from N26, pressed Approve, and the QR and copy buttons showed beside the invoice PDF. Pass.
- Real payment (manual): the owner scanned the QR in the N26 app and it filled the transfer (2026-10-16). **Moved to 001/13** at the owner's request (2026-10-16): the invoice turning paid after the next bank sync.

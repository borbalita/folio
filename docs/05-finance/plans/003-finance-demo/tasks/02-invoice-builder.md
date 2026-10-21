# 003/02 — Vendor catalogue, PDF writer and email builder

## Goal
Code that produces a realistic, fictional invoice email with a PDF, for each kind: Normal, Already paid, Online only.

## Scope
- `app/demo/catalogue.py`: about 6 fictional vendors (name, `.example` sender address, street, IBAN seed, typical amount range, line-item wording), German.
- `app/demo/pdf.py`: a minimal PDF 1.4 writer for one A4 page of text and lines with a standard font; no dependency.
- `app/demo/emails.py`: builds a `ParsedMessage` with a fresh Message-ID, subject, body and `Rechnung_<number>.pdf`; draws amount, invoice number, invoice and due dates, and an IBAN with a valid checksum. Already paid says the amount was debited; Online only is a notice without a PDF that the invoice waits in the customer account (changed 2026-10-21).
- Variance (added 2026-10-21 at the owner's request): each vendor has its own layout (three layouts), number format, payment terms, VAT and email tone; each draw varies the line items and the subject and body wording.
- A seeded random source, so tests are repeatable.

## Out of scope
- Storing or ingesting the email (003/03, 003/04).

## Acceptance criteria
- Given many seeds, then invoices differ in layout, line items and numbers, and emails differ in subject and wording within each vendor's tone. (test)
- Given any seed, when an invoice is built, then its IBAN passes the mod-97 check and its sender domain ends in `.example`. (test)
- Given two builds, then their Message-IDs and invoice numbers differ. (test)
- Given each kind, then the PDF text holds the expected phrases (IBAN for Normal, the debit note for Already paid), and an Online only email carries no PDF and no IBAN. (test)
- Given a built PDF, when opened in the browser's PDF viewer, then it shows a readable invoice. (browser)

## Dependencies
None.

## Notes
- Implementation plan: [02-invoice-builder.plan.md](02-invoice-builder.plan.md).
- Sending the PDF to the extraction model is checked in 003/04.

## Verified

2026-10-21, branch `feat/demo-invoice-builder` (fast suite: 726 passed; ruff clean). Built inline; one independent whole-branch review (four Important findings fixed, test first).

- Valid mod-97 IBANs, sender domains in `.example`: `test_demo_ibans_pass_the_checksum_and_cannot_be_paid` (bank code starts with 0, so no bank accepts a transfer), `test_demo_iban_check_digits`, `test_every_vendor_sends_from_an_example_domain`. Pass.
- Distinct Message-IDs and invoice numbers: `test_messages_get_fresh_ids`. Pass.
- Phrases per kind: `test_pdf_text_per_kind`, `test_already_paid_gives_no_transfer_cue`, `test_online_only_is_a_notice_without_the_invoice`, `test_online_only_body_has_no_iban`. Pass.
- Variance: `test_invoices_vary`, `test_emails_vary`, `test_vendors_differ_in_style`. Pass.
- Totals: `test_drawn_values_are_sane_over_many_seeds` (200 seeds × 3 kinds), `test_totals_in_the_pdf_match`, `test_every_layout_prints_net_vat_and_total_consistently`. Pass.
- Browser: sample PDFs of all three layouts (Havelwatt/classic, Wellenfunk/modern already paid, Kaya & Brandt/compact) opened in the browser pane through a blob iframe, as the app shows them: readable, umlauts, € and the grouped IBAN correct. Pass.
- Vendor names checked by web search on 2026-10-21; "Spreewerk" turned out to be a real company and was replaced by Havelwatt.
- PR: see the branch's pull request.

# 003/02 — Vendor catalogue, PDF writer and email builder

## Goal
Code that produces a realistic, fictional invoice email with a PDF, for each kind: Normal, Already paid, Online only.

## Scope
- `app/demo/catalogue.py`: about 6 fictional vendors (name, `.example` sender address, street, IBAN seed, typical amount range, line-item wording), German.
- `app/demo/pdf.py`: a minimal PDF 1.4 writer for one A4 page of text and lines with a standard font; no dependency.
- `app/demo/emails.py`: builds a `ParsedMessage` with a fresh Message-ID, subject, body and `Rechnung_<number>.pdf`; draws amount, invoice number, invoice and due dates, and an IBAN with a valid checksum. Already paid says the amount was debited; Online only has no IBAN and points to the customer account.
- A seeded random source, so tests are repeatable.

## Out of scope
- Storing or ingesting the email (003/03, 003/04).

## Acceptance criteria
- Given any seed, when an invoice is built, then its IBAN passes the mod-97 check and its sender domain ends in `.example`. (test)
- Given two builds, then their Message-IDs and invoice numbers differ. (test)
- Given each kind, then the PDF text holds the expected phrases (IBAN for Normal, the debit note for Already paid, no IBAN for Online only). (test)
- Given a built PDF, when opened in the browser's PDF viewer, then it shows a readable invoice. (browser)

## Dependencies
None.

## Notes
- Sending the PDF to the extraction model is checked in 003/04.

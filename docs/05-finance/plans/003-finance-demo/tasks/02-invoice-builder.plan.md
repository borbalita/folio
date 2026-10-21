# 003/02 Vendor catalogue, PDF writer and email builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pure code that builds a realistic, fictional German invoice email with a one-page PDF, for the kinds Normal, Already paid and Online only.

**Architecture:** Three small modules under `backend/app/demo/`: a fixed vendor catalogue, a dependency-free PDF writer for text and lines, and a builder that draws invoice values from a seeded `random.Random` and returns an `ingest.email.parse.ParsedMessage` with the PDF attached. No database, no network, no models.

**Tech Stack:** Python 3.12 stdlib (`random`, `decimal`, `datetime`, `uuid`), pytest.

**Spec:** [../README.md](../README.md), task [02-invoice-builder.md](02-invoice-builder.md).

## Global Constraints

- No new dependencies; the PDF is written by hand (PDF 1.4, uncompressed, standard font Helvetica, WinAnsiEncoding).
- Vendors are fictional; sender domains end in `.example` (reserved TLD), so no real company or domain is imitated.
- German wording in subject, body and PDF.
- IBANs pass `app.finance.invoice_checks.iban_valid`. Their bank code starts with `0`, which no German bank uses, so a scanned demo QR can never pay a real account.
- Tests: from `backend/`, `set -a && . ./.env.example && set +a && EMAIL_RERANK=false OPENAI_API_KEY=sk-invalid-for-tests uv run pytest -m "not integration"`; `uv run ruff check .`; `uv run ruff format --check <changed files>`.

## Review Focus

1. **Umlauts, ß and €** in vendor names, line items and amounts must show correctly in the PDF (WinAnsi bytes, `€` is `0x80`) → test in Task 2.
2. **Parentheses and backslashes** in text (e.g. "Strom (Grundversorgung)") must not break the PDF string syntax → test in Task 2.
3. **Due date before invoice date** or amounts with more than 2 decimals must never be drawn → test in Task 3 over many seeds.
4. **German amount format** (`84,20 €`, thousands with `.`) in the PDF and body; the extraction model reads these → test in Task 3.
5. **Online only must not leak an IBAN** anywhere (PDF text and email body) → test in Task 3.

---

### Task 1: Vendor catalogue and demo IBANs

**Files:**
- Create: `backend/app/demo/__init__.py` (empty; 003/01 adds the same empty file, so the merge is clean), `backend/app/demo/catalogue.py`
- Test: `backend/tests/demo/test_catalogue.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True, slots=True) class Vendor: key: str; name: str; sender: str; street: str; city: str; bank_code: str; account: str; amount_range: tuple[Decimal, Decimal]; item: str; customer_portal: str` and `VENDORS: tuple[Vendor, ...]`; `demo_iban(bank_code: str, account: str) -> str` (German IBAN: `DE` + check digits + 8-digit bank code + 10-digit account).
- Catalogue (6 vendors, `key`: name, item): `stadtwerke`: "Stadtwerke Musterstadt GmbH", "Strom (Grundversorgung), Abschlag"; `mobilfunk`: "Funkwelle Mobil GmbH", "Mobilfunk-Tarif Smart M"; `hosting`: "Serverhafen Hosting UG", "Webhosting Paket Pro"; `zahnarzt`: "Zahnarztpraxis Dr. Lindqvist", "Professionelle Zahnreinigung"; `fitness`: "Kraftwerk Fitnessstudio", "Mitgliedsbeitrag"; `handwerk`: "Malerbetrieb Özdemir & Söhne", "Malerarbeiten Flur". Senders like `rechnung@stadtwerke-musterstadt.example` and `service@funkwelle.example`, all ending in `.example`; `customer_portal` e.g. `kundenkonto.funkwelle.example`. Bank codes `0` + 7 digits, distinct per vendor.

- [ ] **Step 1: Write failing tests**
  - `test_every_vendor_sends_from_an_example_domain`: `vendor.sender.endswith(".example")` for all; keys unique; 6 vendors.
  - `test_demo_ibans_pass_the_checksum_and_cannot_be_paid`: for each vendor `iban = demo_iban(v.bank_code, v.account)`; `iban_valid(iban)`; `iban.startswith("DE")`; `len(iban) == 22`; `iban[4] == "0"`.
  - `test_demo_iban_check_digits`: `demo_iban("37040044", "0532013000") == "DE89370400440532013000"` (the standard documentation example proves the check-digit formula).
  - `test_amount_ranges_are_positive_and_ordered`.
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement.** Check digits: `98 - int(numeric(bban + "DE00")) % 97`, zero-padded to 2, where letters map to `ord(c) - 55`.
- [ ] **Step 4: Tests and ruff green.**
- [ ] **Step 5: Commit** `feat(demo): fictional vendor catalogue and unpayable demo IBANs`

---

### Task 2: One-page PDF writer

**Files:**
- Create: `backend/app/demo/pdf.py`
- Test: `backend/tests/demo/test_pdf.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True, slots=True) class Text: x: float; y: float; text: str; size: float = 10; bold: bool = False`; `@dataclass(frozen=True, slots=True) class Rule: y: float; x0: float = 56; x1: float = 539`; `render_pdf(items: Sequence[Text | Rule]) -> bytes`. Coordinates in points on A4 (595 × 842), origin bottom left. Fonts: Helvetica and Helvetica-Bold, both `/Encoding /WinAnsiEncoding`.
- Test helper (in the test module, not app code): `pdf_strings(pdf: bytes) -> list[str]` that decodes every `(...) Tj` string back from cp1252 with `\(`, `\)`, `\\` unescaped.

- [ ] **Step 1: Write failing tests**
  - `test_pdf_has_header_xref_and_trailer`: starts with `b"%PDF-1.4"`, ends with `b"%%EOF\n"`; every xref offset points at `b"<n> 0 obj"`; `startxref` points at `b"xref"`.
  - `test_text_round_trips_with_umlauts_and_euro`: `render_pdf([Text(56, 800, "Malerbetrieb Özdemir & Söhne – 1.234,50 €, Straße")])` → `pdf_strings` returns exactly that text (the en dash is in WinAnsi too).
  - `test_parentheses_and_backslashes_are_escaped`: `"Strom (Grundversorgung) C:\\x"` round-trips and the raw bytes contain `\\(`.
  - `test_rule_draws_a_line`: the content stream contains `56 700 m 539 700 l S` for `Rule(700)`.
  - `test_text_outside_winansi_is_refused`: a character like `"✓"` raises `ValueError` (better than a silently broken PDF).
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement** objects in order: catalog, pages, page (MediaBox `[0 0 595 842]`, resources F1/F2), content stream with `BT /F1 10 Tf x y Td (…) Tj ET` per text and `x0 y m x1 y l S` per rule, two font objects; then xref with 10-digit offsets and the trailer. Encode text with `text.encode("cp1252")`.
- [ ] **Step 4: Tests and ruff green.**
- [ ] **Step 5: Commit** `feat(demo): dependency-free one-page PDF writer`

---

### Task 3: Invoice values and the email builder

**Files:**
- Create: `backend/app/demo/emails.py`
- Test: `backend/tests/demo/test_emails.py`

**Interfaces:**
- Consumes: `Vendor`, `VENDORS`, `demo_iban` (Task 1); `Text`, `Rule`, `render_pdf` (Task 2); `ParsedMessage`, `ParsedAttachment` from `ingest/email/parse.py`.
- Produces (used by 003/03 and 003/04):
  - `InvoiceKind = Literal["normal", "already_paid", "online_only"]`
  - `@dataclass(frozen=True, slots=True) class DemoInvoice: vendor: Vendor; kind: InvoiceKind; number: str; amount: Decimal; invoice_date: date; due_date: date; iban: str | None`
  - `draw_invoice(rng: random.Random, kind: InvoiceKind, today: date, vendor: Vendor | None = None) -> DemoInvoice`: vendor from `rng` when `None`; amount uniform in the vendor's range, quantized to `0.01`; `number = f"RE-{today.year}-{rng.randint(10000, 99999)}"`; `invoice_date = today - rng.randint(0, 3) days`; `due_date = invoice_date + 14 days`; `iban = None` only for `online_only`.
  - `invoice_pdf(invoice: DemoInvoice) -> bytes`: letterhead (vendor name, street, city), recipient "Alex Beispiel, Musterweg 1, 12345 Musterstadt", "Rechnung", number, dates, one line item with amount, total; then per kind: normal → "Bitte überweisen Sie den Betrag bis zum <due> auf folgendes Konto:" with IBAN (grouped in 4s), BIC-free, and "Verwendungszweck: <number>"; already_paid → "Der Betrag wurde am <invoice_date> per Lastschrift von Ihrem Konto abgebucht. Sie müssen nichts weiter tun."; online_only → "Bitte bezahlen Sie bequem in Ihrem Kundenkonto: <customer_portal>".
  - `invoice_message(invoice: DemoInvoice, *, to_address: str, sent_at: datetime) -> ParsedMessage`: `message_id = f"<demo-{uuid4()}@folio.example>"`, `provider_message_id` = the same id, `folder = "INBOX"`, `subject = f"Ihre Rechnung {number} von {vendor.name}"`, `from_address = vendor.sender`, `from_name = vendor.name`, `to_addresses = [to_address]`, German body (greeting, one sentence per kind matching the PDF, "Ihre Rechnung finden Sie im Anhang.", signature), one attachment `Rechnung_<number>.pdf` (`application/pdf`), `attachment_filenames` matching.
  - `format_euro(amount: Decimal) -> str`: German format, `Decimal("1234.5")` → `"1.234,50 €"`.

- [ ] **Step 1: Write failing tests**
  - `test_draw_is_repeatable_for_a_seed`: two `random.Random(7)` draws are equal.
  - `test_drawn_values_are_sane_over_many_seeds`: for seeds 0–199 and each kind: `invoice_date <= today`, `due_date > invoice_date`, `amount == amount.quantize(Decimal("0.01"))`, amount within the vendor's range, IBAN `None` iff `online_only`, else `iban_valid`.
  - `test_messages_get_fresh_ids`: two messages from the same invoice differ in `message_id`; two draws with different seeds differ in `number`.
  - `test_pdf_text_per_kind`: using `pdf_strings` from `tests/demo/test_pdf.py` (move it to `tests/demo/conftest.py` or a `tests/demo/pdf_text.py` helper): normal holds the grouped IBAN and "Verwendungszweck"; already_paid holds "abgebucht" and no "überweisen"; online_only holds the portal and no "DE" IBAN pattern (`re.search(r"DE\d{2}( ?\d{4}){4} ?\d{2}", text)` is `None`).
  - `test_online_only_body_has_no_iban`: same regex on `message.body`.
  - `test_message_shape`: subject, sender ends in `.example`, one attachment named `Rechnung_<number>.pdf` with `application/pdf` and bytes starting `%PDF-1.4`, `attachment_filenames == (that name,)`, `to_addresses == [to_address]`.
  - `test_format_euro`: `"84,20 €"`, `"1.234,50 €"`, `"0,99 €"`.
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement.** Dates in the PDF and body as `dd.mm.yyyy`.
- [ ] **Step 4: Full fast suite and ruff green.**
- [ ] **Step 5: Commit** `feat(demo): invoice emails with PDFs for each demo kind`

---

### Task 4: Verify and record (controller)

- [ ] Every `(test)` criterion in [02-invoice-builder.md](02-invoice-builder.md) maps to a passing test.
- [ ] `(browser)`: write one PDF per kind to a scratch directory, serve it with `python -m http.server` on a free localhost port, open each in the browser pane, and note that it shows a readable invoice (umlauts, €, IBAN grouping).
- [ ] Verified section in the task file; tick 003/02 in the spec only if all passed.

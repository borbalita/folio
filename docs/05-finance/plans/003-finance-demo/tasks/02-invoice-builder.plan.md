# 003/02 Vendor catalogue, PDF writer and email builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pure code that builds a realistic, fictional German invoice email with a one-page PDF, for the kinds Normal, Already paid and Online only.

**Architecture:** Three small modules under `backend/app/demo/`: a fixed vendor catalogue, a dependency-free PDF writer for text and lines, and a builder that draws invoice values from a seeded `random.Random` and returns an `ingest.email.parse.ParsedMessage` with the PDF attached. No database, no network, no models.

**Tech Stack:** Python 3.12 stdlib (`random`, `decimal`, `datetime`, `uuid`), pytest.

**Spec:** [../README.md](../README.md), task [02-invoice-builder.md](02-invoice-builder.md).

## Global Constraints

- No new dependencies; the PDF is written by hand (PDF 1.4, uncompressed, standard font Helvetica, WinAnsiEncoding).
- Vendors sound real but are invented: plausible brand names (checked on 2026-10-21 that no company by that name turned up), real cities, invented street numbers; sender domains end in `.example` (reserved TLD), so no real company or domain is imitated. Never use a real company name, e.g. "Stadtwerke <city>".
- German wording in subject, body and PDF.
- Invoices and emails vary: each vendor has its own layout, number format, payment terms, VAT, line items and email tone, and every draw varies within that (number of items, wording). Every attachment filename still contains `Rechnung`, so the existing filename rule backs up labelling.
- Totals add up: sum of line items (net) + VAT = total, each rounded to cents.
- IBANs pass `app.finance.invoice_checks.iban_valid`. Their bank code starts with `0`, which no German bank uses, so a scanned demo QR can never pay a real account.
- Tests: from `backend/`, `set -a && . ./.env.example && set +a && EMAIL_RERANK=false OPENAI_API_KEY=sk-invalid-for-tests uv run pytest -m "not integration"`; `uv run ruff check .`; `uv run ruff format --check <changed files>`.

## Review Focus

1. **Umlauts, ß and €** in vendor names, line items and amounts must show correctly in the PDF (WinAnsi bytes, `€` is `0x80`) → test in Task 2.
2. **Parentheses and backslashes** in text (e.g. "Strom (Grundversorgung)") must not break the PDF string syntax → test in Task 2.
3. **Due date before invoice date** or amounts with more than 2 decimals must never be drawn → test in Task 3 over many seeds.
4. **German amount format** (`84,20 €`, thousands with `.`) in the PDF and body; the extraction model reads these → test in Task 3.
5. **Online only must not leak an IBAN** anywhere (PDF text and email body) → test in Task 3.
6. **Variance collapsing**: a code change that makes every invoice look the same would still pass the shape tests → variance tests in Task 3 count distinct subjects, openings, layouts and item counts over many seeds.

---

### Task 1: Vendor catalogue and demo IBANs

**Files:**
- Create: `backend/app/demo/__init__.py` (empty; 003/01 adds the same empty file, so the merge is clean), `backend/app/demo/catalogue.py`
- Test: `backend/tests/demo/test_catalogue.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True, slots=True) class Item: label: str; price_range: tuple[Decimal, Decimal]`; `@dataclass(frozen=True, slots=True) class Vendor: key: str; name: str; sender: str; street: str; city: str; bank_code: str; account: str; items: tuple[Item, ...]; max_items: int; vat_rate: Decimal; number_format: str; due_days: int; layout: Literal["classic", "modern", "compact"]; tone: Literal["formal", "friendly", "short"]; filename: str; customer_portal: str` and `VENDORS: tuple[Vendor, ...]`; `demo_iban(bank_code: str, account: str) -> str` (German IBAN: `DE` + check digits + 8-digit bank code + 10-digit account).
- Catalogue (6 vendors; each with 2–5 items, `max_items` 1–4, its own style):

  | key | name | items (examples) | VAT | number format | due | layout | tone | filename |
  |---|---|---|---|---|---|---|---|---|
  | `strom` | Havelwatt Energie GmbH, Potsdam | Abschlag Strom, Grundpreis, Zählermiete | 19 % | `{year}-{n:08d}` | 14 days | classic | formal | `Rechnung_{number}.pdf` |
  | `mobilfunk` | Wellenfunk Mobil GmbH, Düsseldorf | Tarif Smart M, EU-Roaming, Datenpaket 5 GB | 19 % | `FM{n:010d}` | 10 days | modern | friendly | `Wellenfunk_Rechnung_{month}.pdf` |
  | `hosting` | Nordhafen Hosting UG, Hamburg | Webhosting Pro, Domain `.de`, SSL-Zertifikat, Backup | 19 % | `INV-{year}-{n:05d}` | 7 days | compact | short | `Rechnung-INV-{number}.pdf` |
  | `zahnarzt` | Zahnarztpraxis Dr. Rothenbach, Köln | Professionelle Zahnreinigung, Kontrolle, Röntgen | 0 % (medical, VAT-exempt) | `{n:04d}/{year}` | 30 days | classic | formal | `Rechnung {number}.pdf` |
  | `fitness` | Eisenhalle Fitness, Leipzig | Mitgliedsbeitrag, Getränkeflatrate, Kurs Yoga | 19 % | `EH-{n:06d}` | 0 days ("sofort fällig") | modern | friendly | `Rechnung_Eisenhalle.pdf` |
  | `handwerk` | Malerfachbetrieb Kaya & Brandt, Frankfurt am Main | Malerarbeiten Flur (Std.), Material, Anfahrt | 19 % | `R{year}{n:04d}` | 14 days | compact | formal | `Rechnung_{number}.pdf` |

  `{n}` is drawn per invoice; `{month}` is the invoice month (`2026-10`). Senders like `rechnung@havelwatt.example` and `service@wellenfunk.example`, all ending in `.example`; `customer_portal` e.g. `mein.wellenfunk.example`. Bank codes `0` + 7 digits, distinct per vendor.

- [ ] **Step 1: Write failing tests**
  - `test_every_vendor_sends_from_an_example_domain`: `vendor.sender.endswith(".example")` for all; keys unique; 6 vendors.
  - `test_demo_ibans_pass_the_checksum_and_cannot_be_paid`: for each vendor `iban = demo_iban(v.bank_code, v.account)`; `iban_valid(iban)`; `iban.startswith("DE")`; `len(iban) == 22`; `iban[4] == "0"`.
  - `test_demo_iban_check_digits`: `demo_iban("37040044", "0532013000") == "DE89370400440532013000"` (the standard documentation example proves the check-digit formula).
  - `test_item_price_ranges_are_positive_and_ordered`; `1 <= max_items <= len(items)`.
  - `test_vendors_differ_in_style`: at least 3 distinct layouts, 3 tones, 5 number formats, 2 VAT rates across `VENDORS`; every `filename` contains `Rechnung`.
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
  - `test_text_round_trips_with_umlauts_and_euro`: `render_pdf([Text(56, 800, "Zahnarztpraxis Dr. Rothenbach, Köln – 1.234,50 €, Hauptstraße")])` → `pdf_strings` returns exactly that text (the en dash is in WinAnsi too).
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
  - `@dataclass(frozen=True, slots=True) class Line: label: str; quantity: int; unit_price: Decimal` (net)
  - `@dataclass(frozen=True, slots=True) class DemoInvoice: vendor: Vendor; kind: InvoiceKind; number: str; lines: tuple[Line, ...]; net: Decimal; vat: Decimal; amount: Decimal; invoice_date: date; due_date: date; iban: str | None; customer_number: str`
  - `draw_invoice(rng: random.Random, kind: InvoiceKind, today: date, vendor: Vendor | None = None) -> DemoInvoice`: vendor from `rng` when `None`; 1..`max_items` distinct items, each with quantity 1 (hourly items 1–8) and a unit price uniform in its range, quantized to `0.01`; `net` = sum, `vat = (net * vat_rate).quantize(0.01, ROUND_HALF_UP)`, `amount = net + vat`; `number` from the vendor's `number_format`; `invoice_date = today - rng.randint(0, 3)` days; `due_date = invoice_date + due_days`; `customer_number` like `KD-{6 digits}`; `iban = None` only for `online_only`.
  - `invoice_pdf(invoice: DemoInvoice) -> bytes`, addressed to the demo persona `RECIPIENT = ("Kim Albrecht", "Lindenstraße 12", "10969 Berlin")`, laid out per `vendor.layout`:
    - **classic**: letterhead top left, recipient window block, "Rechnung" heading, a meta block (Rechnungsnummer, Kundennummer, Rechnungsdatum), an item table (Pos., Bezeichnung, Menge, Einzelpreis, Gesamt) with rules, net/VAT/total block, footer with bank details and register line.
    - **modern**: name large top right, "RECHNUNG" in bold, meta in two columns, items without position numbers, the total emphasised in bold, bank details inline above the footer.
    - **compact**: one-line letterhead, meta on one line, items as "label … amount" lines, only "Gesamtbetrag (inkl. MwSt.)", payment text directly under it.
    - VAT 0 %: "Umsatzsteuerfrei gem. § 4 Nr. 14 UStG" instead of a VAT line.
    - Payment text per kind, with wording varying per tone: normal → a transfer request until the due date (or "sofort fällig" when `due_days == 0`) with the IBAN grouped in 4s and a reference: "Verwendungszweck: {number}" or "Bitte geben Sie als Referenz {customer_number} / {number} an"; already_paid → the amount "wurde am {date} per Lastschrift von Ihrem Konto abgebucht" (date = invoice date or the next day); online_only → pay in the customer account at `customer_portal`.
  - `invoice_message(invoice: DemoInvoice, *, rng: random.Random, to_address: str, sent_at: datetime) -> ParsedMessage`: `message_id = f"<demo-{uuid4()}@folio.example>"`, `provider_message_id` = the same id, `folder = "INBOX"`, `from_address = vendor.sender`, `from_name = vendor.name`, `to_addresses = [to_address]`, one attachment named by `vendor.filename` (`application/pdf`), `attachment_filenames` matching. Subject and body are drawn with `rng` from small pools per tone (at least 3 subjects and 3 openings per tone), for example:
    - formal: "Ihre Rechnung Nr. {number}", "Rechnung {number} vom {date}"; "Sehr geehrte Damen und Herren," … "Mit freundlichen Grüßen"
    - friendly: "Deine Rechnung für {month_name} ist da", "Neue Rechnung von {vendor}"; "Hallo," … "Viele Grüße, dein {vendor}-Team"
    - short: "Rechnung {number}", "[{vendor}] Rechnung {number}"; a two-line body ("anbei die Rechnung … Zahlung bis {due}.")
    - The body repeats the kind's key fact (amount and due date for normal, "bereits abgebucht" for already_paid, the portal for online_only) and never an IBAN for online_only.
  - `format_euro(amount: Decimal) -> str`: German format, `Decimal("1234.5")` → `"1.234,50 €"`.

- [ ] **Step 1: Write failing tests**
  - `test_draw_is_repeatable_for_a_seed`: two `random.Random(7)` draws are equal.
  - `test_drawn_values_are_sane_over_many_seeds`: for seeds 0–199 and each kind: `invoice_date <= today`, `due_date >= invoice_date`, all money quantized to cents, `net == sum(quantity * unit_price)`, `amount == net + vat`, `vat == 0` iff the vendor's rate is 0, 1 ≤ lines ≤ `max_items` with distinct labels, IBAN `None` iff `online_only`, else `iban_valid`.
  - `test_invoices_vary`: over seeds 0–99 for one vendor: at least 2 distinct line counts and 20 distinct numbers; over all vendors: all 3 layouts appear.
  - `test_emails_vary`: over seeds 0–59 per tone: at least 3 distinct subjects and 3 distinct first body lines; formal bodies never start with "Hallo".
  - `test_totals_in_the_pdf_match`: the PDF text holds `format_euro(amount)`, and for 19 % vendors also `format_euro(vat)`; for the dentist "Umsatzsteuerfrei".
  - `test_messages_get_fresh_ids`: two messages from the same invoice differ in `message_id`; two draws with different seeds differ in `number`.
  - `test_pdf_text_per_kind`: using `pdf_strings` from `tests/demo/test_pdf.py` (move it to `tests/demo/conftest.py` or a `tests/demo/pdf_text.py` helper): normal holds the grouped IBAN and "Verwendungszweck"; already_paid holds "abgebucht" and no "überweisen"; online_only holds the portal and no "DE" IBAN pattern (`re.search(r"DE\d{2}( ?\d{4}){4} ?\d{2}", text)` is `None`).
  - `test_online_only_body_has_no_iban`: same regex on `message.body`.
  - `test_message_shape`: sender ends in `.example`, one attachment named from `vendor.filename` (contains `Rechnung`) with `application/pdf` and bytes starting `%PDF-1.4`, `attachment_filenames == (that name,)`, `to_addresses == [to_address]`.
  - `test_format_euro`: `"84,20 €"`, `"1.234,50 €"`, `"0,99 €"`.
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement.** Dates as `dd.mm.yyyy`; keep each layout a small function (`_classic`, `_modern`, `_compact`) returning `list[Text | Rule]`, and the text pools as module-level tuples.
- [ ] **Step 4: Full fast suite and ruff green.**
- [ ] **Step 5: Commit** `feat(demo): invoice emails with PDFs for each demo kind`

---

### Task 4: Verify and record (controller)

- [ ] Every `(test)` criterion in [02-invoice-builder.md](02-invoice-builder.md) maps to a passing test.
- [ ] `(browser)`: write one PDF per vendor (all three layouts) and per kind to a scratch directory, serve it with `python -m http.server` on a free localhost port, open each in the browser pane, and note that it shows a readable invoice (umlauts, €, IBAN grouping).
- [ ] Verified section in the task file; tick 003/02 in the spec only if all passed.

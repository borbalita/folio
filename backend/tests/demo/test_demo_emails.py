import random
import re
from datetime import UTC, date, datetime
from decimal import Decimal

from app.demo.catalogue import VENDORS
from app.demo.emails import draw_invoice, format_euro, invoice_message, invoice_pdf
from app.finance.invoice_checks import iban_valid
from tests.demo.pdf_text import pdf_text

TODAY = date(2026, 10, 21)
SENT = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
TO = "demo+1@folio.example"
KINDS = ("normal", "already_paid", "online_only")
IBAN_PATTERN = re.compile(r"DE\d{2}( ?\d{4}){4} ?\d{2}")
CENT = Decimal("0.01")


def _vendor(key: str):
    return next(vendor for vendor in VENDORS if vendor.key == key)


def _message(seed: int, kind: str = "normal", vendor=None):
    rng = random.Random(seed)
    invoice = draw_invoice(rng, kind, TODAY, vendor)
    return invoice, invoice_message(invoice, rng=rng, to_address=TO, sent_at=SENT)


def test_draw_is_repeatable_for_a_seed() -> None:
    assert draw_invoice(random.Random(7), "normal", TODAY) == draw_invoice(
        random.Random(7), "normal", TODAY
    )


def test_drawn_values_are_sane_over_many_seeds() -> None:
    for seed in range(200):
        for kind in KINDS:
            invoice = draw_invoice(random.Random(seed), kind, TODAY)
            vendor = invoice.vendor

            assert invoice.invoice_date <= TODAY
            assert invoice.due_date >= invoice.invoice_date
            for money in (invoice.net, invoice.vat, invoice.amount):
                assert money == money.quantize(CENT)
            assert invoice.net == sum(
                line.quantity * line.unit_price for line in invoice.lines
            )
            assert invoice.amount == invoice.net + invoice.vat
            assert (invoice.vat == 0) == (vendor.vat_rate == 0)
            assert 1 <= len(invoice.lines) <= vendor.max_items
            assert len({line.label for line in invoice.lines}) == len(invoice.lines)
            assert invoice.debit_date <= TODAY
            assert (invoice.iban is None) == (kind == "online_only")
            if invoice.iban is not None:
                assert iban_valid(invoice.iban)


def test_invoices_vary() -> None:
    strom = _vendor("strom")
    invoices = [
        draw_invoice(random.Random(seed), "normal", TODAY, strom) for seed in range(100)
    ]

    assert len({len(invoice.lines) for invoice in invoices}) >= 2
    assert len({invoice.number for invoice in invoices}) >= 20
    layouts = {
        draw_invoice(random.Random(s), "normal", TODAY).vendor.layout
        for s in range(100)
    }
    assert layouts == {"classic", "modern", "compact"}


def test_emails_vary() -> None:
    for tone in ("formal", "friendly", "short"):
        vendors = [vendor for vendor in VENDORS if vendor.tone == tone]
        messages = [
            _message(seed, vendor=vendors[seed % len(vendors)])[1] for seed in range(60)
        ]
        subjects = {re.sub(r"\d", "#", message.subject) for message in messages}
        openings = {message.body.splitlines()[0] for message in messages}

        assert len(subjects) >= 3, tone
        assert len(openings) >= 3, tone
        if tone == "formal":
            assert not any(opening.startswith("Hallo") for opening in openings)


def test_totals_in_the_pdf_match() -> None:
    for vendor in VENDORS:
        invoice = draw_invoice(random.Random(3), "normal", TODAY, vendor)
        text = pdf_text(invoice_pdf(invoice))

        assert format_euro(invoice.amount) in text
        if vendor.vat_rate:
            assert format_euro(invoice.vat) in text
        else:
            assert "Umsatzsteuerfrei" in text


def test_messages_get_fresh_ids() -> None:
    invoice = draw_invoice(random.Random(1), "normal", TODAY)
    first = invoice_message(invoice, rng=random.Random(1), to_address=TO, sent_at=SENT)
    second = invoice_message(invoice, rng=random.Random(1), to_address=TO, sent_at=SENT)

    assert first.message_id != second.message_id
    assert draw_invoice(random.Random(1), "normal", TODAY).number != (
        draw_invoice(random.Random(2), "normal", TODAY).number
    )


def test_pdf_text_per_kind() -> None:
    for vendor in VENDORS:
        normal = draw_invoice(random.Random(5), "normal", TODAY, vendor)
        paid = draw_invoice(random.Random(5), "already_paid", TODAY, vendor)
        online = draw_invoice(random.Random(5), "online_only", TODAY, vendor)
        normal_text = pdf_text(invoice_pdf(normal))
        paid_text = pdf_text(invoice_pdf(paid))
        online_text = pdf_text(invoice_pdf(online))

        grouped = " ".join(
            normal.iban[i : i + 4] for i in range(0, len(normal.iban), 4)
        )
        assert grouped in normal_text
        assert normal.reference in normal_text
        assert "abgebucht" in paid_text
        assert "überweisen" not in paid_text
        assert vendor.customer_portal in online_text
        assert IBAN_PATTERN.search(online_text) is None


def test_online_only_body_has_no_iban() -> None:
    for seed in range(30):
        _, message = _message(seed, "online_only")
        assert IBAN_PATTERN.search(message.body) is None


def test_message_shape() -> None:
    for vendor in VENDORS:
        invoice, message = _message(4, "normal", vendor)
        (attachment,) = message.attachments

        assert message.from_address == vendor.sender
        assert message.from_name == vendor.name
        assert message.from_address.endswith(".example")
        assert "Rechnung" in attachment.filename
        assert "/" not in attachment.filename
        assert attachment.content_type == "application/pdf"
        assert attachment.content.startswith(b"%PDF-1.4")
        assert message.attachment_filenames == (attachment.filename,)
        assert message.to_addresses == [TO]
        assert message.provider_message_id == message.message_id
        assert message.sent_at == SENT
        assert format_euro(invoice.amount) in message.body


def test_format_euro() -> None:
    assert format_euro(Decimal("84.2")) == "84,20 €"
    assert format_euro(Decimal("1234.5")) == "1.234,50 €"
    assert format_euro(Decimal("0.99")) == "0,99 €"


def test_every_layout_prints_net_vat_and_total_consistently() -> None:
    for vendor in VENDORS:
        invoice = draw_invoice(random.Random(9), "normal", TODAY, vendor)
        text = pdf_text(invoice_pdf(invoice))

        assert format_euro(invoice.amount) in text
        if vendor.vat_rate:
            assert format_euro(invoice.net) in text, vendor.key
            assert "zzgl." in text, vendor.key
            assert "enthält" not in text, vendor.key


def test_already_paid_gives_no_transfer_cue() -> None:
    for vendor in VENDORS:
        rng = random.Random(6)
        invoice = draw_invoice(rng, "already_paid", TODAY, vendor)
        message = invoice_message(invoice, rng=rng, to_address=TO, sent_at=SENT)
        text = pdf_text(invoice_pdf(invoice))

        assert IBAN_PATTERN.search(text) is None, vendor.key
        assert "Mandatsreferenz" in text, vendor.key
        assert "überweis" not in text + message.body, vendor.key


def test_normal_body_names_the_same_reference_as_the_pdf() -> None:
    for seed in range(40):
        invoice, message = _message(seed, "normal")
        if invoice.vendor.tone == "formal":
            assert invoice.reference in message.body
            assert "Angabe der Rechnungsnummer" not in message.body


def test_online_only_is_a_notice_without_the_invoice() -> None:
    for vendor in VENDORS:
        invoice, message = _message(8, "online_only", vendor)

        assert message.attachments == ()
        assert message.attachment_filenames == ()
        assert vendor.customer_portal in message.body
        assert format_euro(invoice.amount) in message.body
        assert invoice.number in message.body
        assert "Anhang" not in message.body
        assert "anbei" not in message.body
        assert IBAN_PATTERN.search(message.body) is None

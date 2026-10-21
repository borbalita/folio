"""Draw a demo invoice and build its email in the vendor's layout and tone.

Normal and already-paid emails carry the invoice PDF; an online-only email is a notice that
the invoice waits in the customer account, as the ingest check defines `online_only`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import uuid4

from app.demo.catalogue import VENDORS, Vendor, demo_iban
from app.demo.pdf import Rule, Text, render_pdf
from ingest.email.parse import ParsedAttachment, ParsedMessage

InvoiceKind = Literal["normal", "already_paid", "online_only"]

CENT = Decimal("0.01")
RECIPIENT = ("Kim Albrecht", "Lindenstraße 12", "10969 Berlin")
MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Line:
    label: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return self.quantity * self.unit_price


@dataclass(frozen=True, slots=True)
class DemoInvoice:
    vendor: Vendor
    kind: InvoiceKind
    number: str
    lines: tuple[Line, ...]
    net: Decimal
    vat: Decimal
    amount: Decimal
    invoice_date: date
    due_date: date
    iban: str | None
    customer_number: str
    reference: str
    debit_date: date


def format_euro(amount: Decimal) -> str:
    us = f"{amount.quantize(CENT):,.2f}"
    return us.replace(",", " ").replace(".", ",").replace(" ", ".") + " €"


def _date(value: date) -> str:
    return f"{value:%d.%m.%Y}"


def _price(rng: random.Random, low: Decimal, high: Decimal) -> Decimal:
    return (low + (high - low) * Decimal(rng.random())).quantize(CENT)


def draw_invoice(
    rng: random.Random, kind: InvoiceKind, today: date, vendor: Vendor | None = None
) -> DemoInvoice:
    vendor = vendor or rng.choice(VENDORS)
    items = rng.sample(vendor.items, rng.randint(1, vendor.max_items))
    lines = tuple(
        Line(
            item.label,
            rng.randint(1, 8) if "(Std.)" in item.label else 1,
            _price(rng, *item.price_range),
        )
        for item in items
    )
    net = sum((line.total for line in lines), Decimal(0))
    vat = (net * vendor.vat_rate).quantize(CENT, ROUND_HALF_UP)
    invoice_date = today - timedelta(days=rng.randint(0, 3))
    number = vendor.number_format.format(
        year=invoice_date.year, n=rng.randint(100, 99999)
    )
    customer_number = f"KD-{rng.randint(100000, 999999)}"
    return DemoInvoice(
        vendor=vendor,
        kind=kind,
        number=number,
        lines=lines,
        net=net,
        vat=vat,
        amount=net + vat,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=vendor.due_days),
        iban=None
        if kind == "online_only"
        else demo_iban(vendor.bank_code, vendor.account),
        customer_number=customer_number,
        reference=rng.choice((number, f"{customer_number} / {number}")),
        # Already debited, so never later than today.
        debit_date=min(invoice_date + timedelta(days=rng.randint(0, 1)), today),
    )


def _grouped(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _vat_line(invoice: DemoInvoice) -> tuple[str, str]:
    if not invoice.vendor.vat_rate:
        return ("Umsatzsteuerfrei gem. § 4 Nr. 14 UStG", "")
    return (
        f"zzgl. {invoice.vendor.vat_rate * 100:.0f} % USt.",
        format_euro(invoice.vat),
    )


def _payment_lines(invoice: DemoInvoice) -> list[str]:
    """What to do about the money, in the vendor's tone; no IBAN for online-only invoices."""
    tone, amount = invoice.vendor.tone, format_euro(invoice.amount)
    due = (
        "sofort"
        if invoice.vendor.due_days == 0
        else f"bis zum {_date(invoice.due_date)}"
    )
    if invoice.kind == "already_paid":
        return {
            "formal": [
                f"Der Betrag von {amount} wurde am {_date(invoice.debit_date)} per Lastschrift",
                "von Ihrem Konto abgebucht. Sie müssen nichts weiter tun.",
            ],
            "friendly": [
                f"Wir haben {amount} am {_date(invoice.debit_date)} per Lastschrift abgebucht –",
                "du musst nichts weiter tun.",
            ],
            "short": [
                f"Betrag wurde am {_date(invoice.debit_date)} per Lastschrift abgebucht."
            ],
        }[tone]
    portal = invoice.vendor.customer_portal
    if invoice.kind == "online_only":
        return {
            "formal": [
                f"Bitte begleichen Sie den Betrag von {amount} {due}",
                f"in Ihrem Kundenkonto unter {portal}.",
            ],
            "friendly": [
                f"Bezahl {amount} ganz bequem {due} in deinem Kundenkonto: {portal}"
            ],
            "short": [f"Zahlung {due} online im Kundenkonto: {portal}"],
        }[tone]
    assert invoice.iban is not None
    account = f"{invoice.vendor.name} · IBAN {_grouped(invoice.iban)}"
    if invoice.reference == invoice.number:
        reference = f"Verwendungszweck: {invoice.number}"
    elif tone == "friendly":
        reference = f"Bitte gib als Referenz {invoice.reference} an."
    else:
        reference = f"Bitte geben Sie als Referenz {invoice.reference} an."
    first = {
        "formal": f"Bitte überweisen Sie den Betrag von {amount} {due} auf folgendes Konto:",
        "friendly": f"Bitte überweise {amount} {due} an:",
        "short": f"Zahlbar {due} an:",
    }[tone]
    return [first, account, reference]


def _footer(invoice: DemoInvoice) -> list[Text]:
    vendor = invoice.vendor
    city = vendor.city.split(" ", 1)[1]
    items = [
        Text(56, 60, f"{vendor.name} · {vendor.street} · {vendor.city}", 7),
        Text(
            56,
            50,
            f"Registergericht: Amtsgericht {city} · Steuernr. 27/{vendor.account[:3]}/{vendor.account[3:8]}",
            7,
        ),
    ]
    if invoice.kind == "normal":
        iban = demo_iban(vendor.bank_code, vendor.account)
        items.append(Text(56, 40, f"Bankverbindung: IBAN {_grouped(iban)}", 7))
    elif invoice.kind == "already_paid":
        # A direct-debit footer, so nothing on the page reads like a transfer request.
        items.append(
            Text(
                56,
                40,
                f"Gläubiger-ID DE98ZZZ0{vendor.account[:9]} · "
                f"Mandatsreferenz {invoice.customer_number}",
                7,
            )
        )
    return items


def _classic(invoice: DemoInvoice) -> list[Text | Rule]:
    vendor = invoice.vendor
    out: list[Text | Rule] = [
        Text(56, 790, vendor.name, 14, bold=True),
        Text(56, 776, f"{vendor.street} · {vendor.city}", 9),
        Text(56, 718, f"{vendor.name} · {vendor.street} · {vendor.city}", 7),
        *(Text(56, 700 - 14 * i, line) for i, line in enumerate(RECIPIENT)),
        Text(360, 700, f"Rechnungsnummer: {invoice.number}", 9),
        Text(360, 686, f"Kundennummer: {invoice.customer_number}", 9),
        Text(360, 672, f"Rechnungsdatum: {_date(invoice.invoice_date)}", 9),
        Text(56, 620, "Rechnung", 16, bold=True),
        Text(56, 590, "Pos.", 9, bold=True),
        Text(90, 590, "Bezeichnung", 9, bold=True),
        Text(330, 590, "Menge", 9, bold=True),
        Text(390, 590, "Einzelpreis", 9, bold=True),
        Text(480, 590, "Gesamt", 9, bold=True),
        Rule(584),
    ]
    y = 570
    for position, line in enumerate(invoice.lines, start=1):
        out += [
            Text(56, y, str(position), 9),
            Text(90, y, line.label, 9),
            Text(330, y, str(line.quantity), 9),
            Text(390, y, format_euro(line.unit_price), 9),
            Text(480, y, format_euro(line.total), 9),
        ]
        y -= 16
    vat_label, vat_value = _vat_line(invoice)
    out += [
        Rule(y + 8),
        Text(330, y - 8, "Nettobetrag", 9),
        Text(480, y - 8, format_euro(invoice.net), 9),
        Text(330, y - 22, vat_label, 9),
        Text(480, y - 22, vat_value, 9),
        Text(330, y - 40, "Gesamtbetrag", 10, bold=True),
        Text(480, y - 40, format_euro(invoice.amount), 10, bold=True),
    ]
    out += [
        Text(56, y - 80 - 14 * i, line)
        for i, line in enumerate(_payment_lines(invoice))
    ]
    return out + _footer(invoice)


def _modern(invoice: DemoInvoice) -> list[Text | Rule]:
    vendor = invoice.vendor
    due = "sofort" if vendor.due_days == 0 else _date(invoice.due_date)
    out: list[Text | Rule] = [
        Text(300, 790, vendor.name, 18, bold=True),
        Text(300, 772, vendor.street, 9),
        Text(300, 760, vendor.city, 9),
        Text(56, 720, "RECHNUNG", 22, bold=True),
        Text(56, 690, "Rechnungsnr.", 9),
        Text(140, 690, invoice.number, 9, bold=True),
        Text(320, 690, "Datum", 9),
        Text(380, 690, _date(invoice.invoice_date), 9),
        Text(56, 674, "Kundennr.", 9),
        Text(140, 674, invoice.customer_number, 9),
        Text(320, 674, "Fällig", 9),
        Text(380, 674, due, 9),
        Text(56, 640, "An", 8),
        *(Text(56, 626 - 13 * i, line) for i, line in enumerate(RECIPIENT)),
        Rule(570),
    ]
    y = 552
    for line in invoice.lines:
        label = line.label if line.quantity == 1 else f"{line.label} × {line.quantity}"
        out += [Text(56, y, label), Text(470, y, format_euro(line.total))]
        y -= 18
    vat_label, vat_value = _vat_line(invoice)
    out += [
        Rule(y + 6),
        Text(330, y - 10, "Netto", 9),
        Text(470, y - 10, format_euro(invoice.net), 9),
        Text(330, y - 24, vat_label, 9),
        Text(470, y - 24, vat_value, 9),
        Text(330, y - 48, "Gesamt", 14, bold=True),
        Text(470, y - 48, format_euro(invoice.amount), 14, bold=True),
    ]
    out += [
        Text(56, 140 - 14 * i, line, 9)
        for i, line in enumerate(_payment_lines(invoice))
    ]
    return out + _footer(invoice)


def _compact(invoice: DemoInvoice) -> list[Text | Rule]:
    vendor = invoice.vendor
    out: list[Text | Rule] = [
        Text(
            56, 800, f"{vendor.name} · {vendor.street} · {vendor.city}", 10, bold=True
        ),
        Rule(792),
        Text(56, 770, "An: " + ", ".join(RECIPIENT), 9),
        Text(
            56,
            750,
            f"Rechnung {invoice.number} · {_date(invoice.invoice_date)} · Kd.-Nr. {invoice.customer_number}",
            9,
            bold=True,
        ),
    ]
    y = 720
    for line in invoice.lines:
        label = line.label if line.quantity == 1 else f"{line.quantity} × {line.label}"
        out += [Text(56, y, f"{label} …", 9), Text(470, y, format_euro(line.total), 9)]
        y -= 14
    if vendor.vat_rate:
        total = (
            f"Gesamtbetrag: {format_euro(invoice.amount)} (Netto {format_euro(invoice.net)}"
            f" zzgl. {vendor.vat_rate * 100:.0f} % USt. {format_euro(invoice.vat)})"
        )
    else:
        total = f"Gesamtbetrag: {format_euro(invoice.amount)} – Umsatzsteuerfrei gem. § 4 Nr. 14 UStG"
    out += [Rule(y + 6), Text(56, y - 10, total, 10, bold=True)]
    out += [
        Text(56, y - 30 - 13 * i, line, 9)
        for i, line in enumerate(_payment_lines(invoice))
    ]
    return out + _footer(invoice)


_LAYOUTS = {"classic": _classic, "modern": _modern, "compact": _compact}


def invoice_pdf(invoice: DemoInvoice) -> bytes:
    return render_pdf(_LAYOUTS[invoice.vendor.layout](invoice))


SUBJECTS = {
    "formal": (
        "Ihre Rechnung Nr. {number}",
        "Rechnung {number} vom {date}",
        "Ihre Rechnung von {vendor}",
        "Rechnungsstellung {month} {year}",
    ),
    "friendly": (
        "Deine Rechnung für {month} ist da",
        "Neue Rechnung von {brand}",
        "Deine {brand}-Rechnung {number}",
    ),
    "short": (
        "Rechnung {number}",
        "[{brand}] Rechnung {number}",
        "Neue Rechnung verfügbar: {number}",
    ),
}
OPENINGS = {
    "formal": (
        "Sehr geehrte Damen und Herren,",
        "Guten Tag Kim Albrecht,",
        "Sehr geehrte Kundin, sehr geehrter Kunde,",
    ),
    "friendly": ("Hallo Kim,", "Hi Kim,", "Hallo,"),
    "short": ("Guten Tag,", "Hallo,", "Moin,"),
}


def _key_fact(invoice: DemoInvoice) -> str:
    tone, amount = invoice.vendor.tone, format_euro(invoice.amount)
    due = (
        "sofort"
        if invoice.vendor.due_days == 0
        else f"bis zum {_date(invoice.due_date)}"
    )
    portal = invoice.vendor.customer_portal
    facts = {
        "normal": {
            "formal": (
                f"Bitte überweisen Sie den Betrag {due} mit der Referenz {invoice.reference}."
            ),
            "friendly": f"Bitte überweise den Betrag {due}.",
            "short": f"Zahlbar {due}.",
        },
        "already_paid": {
            "formal": "Der Betrag wurde bereits per Lastschrift abgebucht, Sie müssen nichts tun.",
            "friendly": "Den Betrag haben wir schon per Lastschrift abgebucht – du musst nichts tun.",
            "short": "Betrag wird per Lastschrift abgebucht.",
        },
        "online_only": {
            "formal": f"Bitte bezahlen Sie den Betrag {due} in Ihrem Kundenkonto unter {portal}.",
            "friendly": f"Bezahlen kannst du {due} ganz einfach in deinem Kundenkonto: {portal}",
            "short": f"Zahlung {due} online unter {portal}.",
        },
    }
    if invoice.kind == "online_only":
        # A notice only: the invoice itself waits in the customer account.
        lead = {
            "formal": f"Ihre Rechnung {invoice.number} über {amount} steht für Sie bereit.",
            "friendly": f"deine Rechnung {invoice.number} über {amount} ist jetzt online.",
            "short": f"Rechnung {invoice.number} über {amount} ist online abrufbar.",
        }[tone]
    else:
        lead = {
            "formal": f"anbei erhalten Sie unsere Rechnung {invoice.number} über {amount}.",
            "friendly": f"im Anhang findest du deine Rechnung {invoice.number} über {amount}.",
            "short": f"anbei die Rechnung {invoice.number} über {amount}.",
        }[tone]
    return f"{lead} {facts[invoice.kind][tone]}"


def _body(invoice: DemoInvoice, opening: str) -> str:
    vendor, brand = invoice.vendor, invoice.vendor.name.split()[0]
    closing = {
        "formal": f"Mit freundlichen Grüßen\n{vendor.name}",
        "friendly": f"Viele Grüße\ndein Team von {brand}",
        "short": "",
    }[vendor.tone]
    return "\n\n".join(part for part in (opening, _key_fact(invoice), closing) if part)


def invoice_message(
    invoice: DemoInvoice, *, rng: random.Random, to_address: str, sent_at: datetime
) -> ParsedMessage:
    vendor = invoice.vendor
    subject = rng.choice(SUBJECTS[vendor.tone]).format(
        number=invoice.number,
        date=_date(invoice.invoice_date),
        vendor=vendor.name,
        brand=vendor.name.split()[0],
        month=MONTHS[invoice.invoice_date.month - 1],
        year=invoice.invoice_date.year,
    )
    attachments: tuple[ParsedAttachment, ...] = ()
    if invoice.kind != "online_only":
        filename = vendor.filename.format(
            number=invoice.number, month=f"{invoice.invoice_date:%Y-%m}"
        ).replace("/", "-")
        attachments = (
            ParsedAttachment(filename, "application/pdf", invoice_pdf(invoice)),
        )
    message_id = f"<demo-{uuid4()}@folio.example>"
    return ParsedMessage(
        message_id=message_id,
        provider_message_id=message_id,
        folder="INBOX",
        subject=subject,
        from_address=vendor.sender,
        from_name=vendor.name,
        to_addresses=[to_address],
        sent_at=sent_at,
        body=_body(invoice, rng.choice(OPENINGS[vendor.tone])),
        attachment_filenames=tuple(attachment.filename for attachment in attachments),
        attachments=attachments,
    )

"""Fictional vendors for the demo user's invoices.

The names sound real but are invented, and every domain uses the reserved `.example`
TLD, so no real company or domain is imitated. Bank codes start with 0, which no German
bank uses: the IBANs pass the checksum, but a scanned demo QR can never pay anyone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Layout = Literal["classic", "modern", "compact"]
Tone = Literal["formal", "friendly", "short"]


@dataclass(frozen=True, slots=True)
class Item:
    label: str
    price_range: tuple[Decimal, Decimal]


@dataclass(frozen=True, slots=True)
class Vendor:
    key: str
    name: str
    sender: str
    street: str
    city: str
    bank_code: str
    account: str
    items: tuple[Item, ...]
    max_items: int
    vat_rate: Decimal
    number_format: str
    due_days: int
    layout: Layout
    tone: Tone
    filename: str
    customer_portal: str


def _item(label: str, low: str, high: str) -> Item:
    return Item(label, (Decimal(low), Decimal(high)))


VENDORS: tuple[Vendor, ...] = (
    Vendor(
        key="strom",
        name="Spreewerk Energie GmbH",
        sender="rechnung@spreewerk-energie.example",
        street="Am Spreeufer 18",
        city="10179 Berlin",
        bank_code="01020304",
        account="4400128801",
        items=(
            _item("Abschlag Strom", "48.00", "96.00"),
            _item("Grundpreis", "9.50", "14.90"),
            _item("Zählermiete", "1.90", "2.90"),
        ),
        max_items=3,
        vat_rate=Decimal("0.19"),
        number_format="{year}-{n:08d}",
        due_days=14,
        layout="classic",
        tone="formal",
        filename="Rechnung_{number}.pdf",
        customer_portal="kundenportal.spreewerk-energie.example",
    ),
    Vendor(
        key="mobilfunk",
        name="Wellenfunk Mobil GmbH",
        sender="service@wellenfunk.example",
        street="Kaiserswerther Straße 207",
        city="40474 Düsseldorf",
        bank_code="03007012",
        account="7720045519",
        items=(
            _item("Tarif Smart M", "19.99", "29.99"),
            _item("EU-Roaming", "2.00", "9.00"),
            _item("Datenpaket 5 GB", "4.99", "7.99"),
        ),
        max_items=3,
        vat_rate=Decimal("0.19"),
        number_format="FM{n:010d}",
        due_days=10,
        layout="modern",
        tone="friendly",
        filename="Wellenfunk_Rechnung_{month}.pdf",
        customer_portal="mein.wellenfunk.example",
    ),
    Vendor(
        key="hosting",
        name="Nordhafen Hosting UG (haftungsbeschränkt)",
        sender="billing@nordhafen-hosting.example",
        street="Großer Grasbrook 9",
        city="20457 Hamburg",
        bank_code="02004506",
        account="0081734620",
        items=(
            _item("Webhosting Pro", "7.90", "14.90"),
            _item("Domain .de", "0.99", "1.49"),
            _item("SSL-Zertifikat", "4.90", "9.90"),
            _item("Tägliches Backup", "1.50", "3.00"),
        ),
        max_items=4,
        vat_rate=Decimal("0.19"),
        number_format="INV-{year}-{n:05d}",
        due_days=7,
        layout="compact",
        tone="short",
        filename="Rechnung-{number}.pdf",
        customer_portal="panel.nordhafen-hosting.example",
    ),
    Vendor(
        key="zahnarzt",
        name="Zahnarztpraxis Dr. Rothenbach",
        sender="praxis@zahnarzt-rothenbach.example",
        street="Dürener Straße 112",
        city="50931 Köln",
        bank_code="03700650",
        account="2210983344",
        items=(
            _item("Professionelle Zahnreinigung", "89.00", "129.00"),
            _item("Kontrolluntersuchung", "25.00", "45.00"),
            _item("Röntgenaufnahme", "18.00", "36.00"),
        ),
        max_items=2,
        vat_rate=Decimal(0),
        number_format="{n:04d}/{year}",
        due_days=30,
        layout="classic",
        tone="formal",
        filename="Rechnung {number}.pdf",
        customer_portal="patienten.zahnarzt-rothenbach.example",
    ),
    Vendor(
        key="fitness",
        name="Eisenhalle Fitness",
        sender="hallo@eisenhalle-fitness.example",
        street="Karl-Heine-Straße 66",
        city="04229 Leipzig",
        bank_code="08608104",
        account="0004417788",
        items=(
            _item("Mitgliedsbeitrag", "29.90", "49.90"),
            _item("Getränkeflatrate", "6.90", "9.90"),
            _item("Kurs Yoga (4 Termine)", "24.00", "36.00"),
        ),
        max_items=3,
        vat_rate=Decimal("0.19"),
        number_format="EH-{n:06d}",
        due_days=0,
        layout="modern",
        tone="friendly",
        filename="Rechnung_Eisenhalle.pdf",
        customer_portal="mitglieder.eisenhalle-fitness.example",
    ),
    Vendor(
        key="handwerk",
        name="Malerfachbetrieb Kaya & Brandt",
        sender="buero@kaya-brandt.example",
        street="Hanauer Landstraße 301",
        city="60314 Frankfurt am Main",
        bank_code="05001020",
        account="6603917425",
        items=(
            _item("Malerarbeiten Flur (Std.)", "48.00", "58.00"),
            _item("Material (Farbe, Abdeckung)", "65.00", "140.00"),
            _item("Anfahrtspauschale", "25.00", "35.00"),
        ),
        max_items=3,
        vat_rate=Decimal("0.19"),
        number_format="R{year}{n:04d}",
        due_days=14,
        layout="compact",
        tone="formal",
        filename="Rechnung_{number}.pdf",
        customer_portal="kunden.kaya-brandt.example",
    ),
)


def demo_iban(bank_code: str, account: str) -> str:
    """A German IBAN with ISO 13616 check digits for this bank code and account."""
    bban = bank_code + account
    rearranged = bban + "DE00"
    digits = "".join(str(int(char, 36)) for char in rearranged)
    check = 98 - int(digits) % 97
    return f"DE{check:02d}{bban}"

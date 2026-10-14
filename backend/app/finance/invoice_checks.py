"""Plausibility checks on invoice payment fields. An invoice is open only when all pass."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal

from app.database.models.finance.invoice import Invoice, InvoiceStatus

# IBAN lengths per country, from the SWIFT IBAN registry.
_IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BI": 27, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24,
    "DE": 22, "DJ": 27, "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18,
    "FK": 18, "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27,
    "GT": 28, "HN": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IQ": 23, "IS": 26,
    "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20,
    "LU": 20, "LV": 21, "LY": 25, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MN": 20,
    "MR": 27, "MT": 31, "MU": 30, "NI": 28, "NL": 18, "NO": 15, "OM": 23, "PK": 24,
    "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "RU": 33, "SA": 24,
    "SC": 31, "SD": 18, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SO": 23, "ST": 25,
    "SV": 28, "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
    "YE": 30,
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class InvoiceFields:
    payee: str | None = None
    iban: str | None = None
    bic: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    invoice_number: str | None = None
    reference: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None


FIELD_NAMES = tuple(field.name for field in fields(InvoiceFields))


def normalize_iban(raw: str) -> str:
    return "".join(raw.split()).upper()


def iban_valid(iban: str) -> bool:
    """Country length and the ISO 13616 mod-97 checksum. Expects a normalized IBAN."""
    if _IBAN_LENGTHS.get(iban[:2]) != len(iban) or not (
        iban.isascii() and iban.isalnum()
    ):
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    return int(digits) % 97 == 1


def check(fields: InvoiceFields) -> tuple[InvoiceStatus, list[str]]:
    """Return the status and the names of the failed checks."""
    issues: list[str] = []
    if not (fields.payee and fields.payee.strip()):
        issues.append("missing_payee")
    if not fields.iban:
        issues.append("missing_iban")
    elif not iban_valid(fields.iban):
        issues.append("invalid_iban")
    if fields.amount is None:
        issues.append("missing_amount")
    elif fields.amount <= 0:
        issues.append("amount_not_positive")
    if fields.currency != "EUR":
        issues.append("currency_not_eur")
    return (InvoiceStatus.NEEDS_INFO if issues else InvoiceStatus.OPEN), issues


def fields_of(row: Invoice) -> InvoiceFields:
    return InvoiceFields(**{name: getattr(row, name) for name in FIELD_NAMES})


def recheck(row: Invoice) -> None:
    """Refresh issues; a paid invoice stays paid whatever its fields say."""
    status, row.issues = check(fields_of(row))
    if row.status != InvoiceStatus.PAID:
        row.status = status

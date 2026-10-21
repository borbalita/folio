"""Owner changes to an invoice: field edits and marking paid. Each re-checks the invoice."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.finance.invoice_checks import FIELD_NAMES, normalize_iban, recheck

PAID_BY_OWNER = "owner"
# Paid because a bank transaction was linked to it, by the rules or by the owner.
PAID_BY_MATCH = "match"
# Paid before it arrived: the invoice itself says so (prepaid, received, debited).
PAID_BY_INVOICE = "invoice"


def apply_edit(row: Invoice, changes: dict[str, Any]) -> None:
    """Set the given fields, remember them as owner-edited, and re-check."""
    edited = list(row.edited_fields or [])
    for name, value in changes.items():
        if name not in FIELD_NAMES:
            raise ValueError(f"{name} is not an invoice field")
        setattr(row, name, _clean(name, value))
        if name not in edited:
            edited.append(name)
    row.edited_fields = edited
    recheck(row)


def set_paid(row: Invoice, *, paid: bool, now: datetime) -> None:
    if paid:
        row.status = InvoiceStatus.PAID
        row.paid_at = now
        row.paid_by = PAID_BY_OWNER
        return
    row.status = InvoiceStatus.OPEN
    row.paid_at = None
    row.paid_by = None
    recheck(row)


def mark_paid_per_invoice(row: Invoice, *, paid_at: datetime) -> None:
    row.status = InvoiceStatus.PAID
    row.paid_at = paid_at
    row.paid_by = PAID_BY_INVOICE


def mark_matched(row: Invoice, *, now: datetime) -> None:
    row.status = InvoiceStatus.PAID
    row.paid_at = now
    row.paid_by = PAID_BY_MATCH


def _clean(name: str, value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip() or None
    if value is None:
        return None
    if name == "iban":
        return normalize_iban(value)
    if name in ("bic", "currency"):
        return value.upper()
    if name == "amount":
        return Decimal(value).quantize(Decimal("0.01"))
    return value

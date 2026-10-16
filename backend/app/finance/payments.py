"""Rules for payment drafts: what is copied from an invoice, and when a draft may be paid."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.finance.invoice_checks import iban_valid, normalize_iban


@dataclass(frozen=True, slots=True)
class DraftValues:
    """What the QR code will carry, frozen when the draft is made."""

    payee: str
    iban: str
    bic: str | None
    amount: Decimal
    currency: str
    reference: str | None


def draft_values(invoice: Invoice) -> DraftValues:
    # The reference the invoice asks for; its number when it asks for none (owner, 2026-10-15).
    return DraftValues(
        payee=invoice.payee or "",
        iban=invoice.iban or "",
        bic=invoice.bic,
        amount=invoice.amount,
        currency=invoice.currency or "",
        reference=invoice.reference or invoice.invoice_number,
    )


def skip_reason(invoice: Invoice) -> str | None:
    """Only open invoices are payable: paid ones are done, needs_info ones lack data."""
    return None if invoice.status == InvoiceStatus.OPEN else "not_open"


def approve_refusal(invoice: Invoice, draft: DraftValues) -> str | None:
    """Why the draft may no longer be paid as frozen, or None."""
    if invoice.status != InvoiceStatus.OPEN:
        return "not_open"
    iban = normalize_iban(invoice.iban or "")
    if not iban_valid(iban):
        return "invalid_iban"
    if iban != normalize_iban(draft.iban):
        return "iban_changed"
    if invoice.amount != draft.amount:
        return "amount_changed"
    return None

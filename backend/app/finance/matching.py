"""Rules that link an invoice to the debit that paid it. No database here."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

WINDOW = timedelta(days=120)
MIN_TOKEN = 4
# Words most company names share; matching on them alone would pair strangers.
_COMMON_WORDS = frozenset(
    {"gmbh", "kgaa", "mbh", "deutschland", "germany", "europe", "service", "services"}
)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")

Status = Literal["linked", "suggested"]


@dataclass(frozen=True, slots=True)
class InvoiceFacts:
    id: uuid.UUID
    amount: Decimal
    currency: str | None
    iban: str | None
    invoice_number: str | None
    reference: str | None
    payee: str | None
    # The invoice date, or the email's date when the invoice has none.
    start: date


@dataclass(frozen=True, slots=True)
class Debit:
    id: uuid.UUID
    booking_date: date
    # Money that left the account, as a positive number.
    amount: Decimal
    currency: str
    counterparty_iban: str | None
    counterparty_name: str | None
    remittance: str


@dataclass(frozen=True, slots=True)
class Proposal:
    invoice_id: uuid.UUID
    transaction_id: uuid.UUID
    status: Status
    signals: tuple[str, ...]


def _compact(text: str | None) -> str:
    return _NON_ALNUM.sub("", (text or "").lower())


def _tokens(text: str | None) -> set[str]:
    words = _NON_ALNUM.split((text or "").lower())
    return {w for w in words if len(w) >= MIN_TOKEN and w not in _COMMON_WORDS}


def signals(invoice: InvoiceFacts, debit: Debit) -> tuple[str, ...]:
    """The signals this debit shares with the invoice; empty unless the amount matches."""
    if debit.amount != invoice.amount or debit.currency != invoice.currency:
        return ()
    found = ["amount"]
    if invoice.iban and _compact(debit.counterparty_iban) == _compact(invoice.iban):
        found.append("iban")
    text = _compact(debit.remittance)
    refs = (_compact(invoice.invoice_number), _compact(invoice.reference))
    if any(len(ref) >= MIN_TOKEN and ref in text for ref in refs):
        found.append("reference")
    if _tokens(invoice.payee) & _tokens(debit.counterparty_name):
        found.append("name")
    return tuple(found)


def _strong(found: tuple[str, ...]) -> bool:
    return "iban" in found or "reference" in found


def propose(
    invoice: InvoiceFacts,
    debits: list[Debit],
    *,
    rejected: set[uuid.UUID],
    taken: set[uuid.UUID],
) -> list[Proposal]:
    """One strong candidate is linked; several strong ones, or only weak ones, are suggestions."""
    candidates: list[tuple[Debit, tuple[str, ...]]] = []
    for debit in debits:
        if debit.id in rejected or debit.id in taken:
            continue
        if not invoice.start <= debit.booking_date <= invoice.start + WINDOW:
            continue
        found = signals(invoice, debit)
        if len(found) > 1:
            candidates.append((debit, found))

    strong = [(d, f) for d, f in candidates if _strong(f)]
    if len(strong) == 1:
        debit, found = strong[0]
        return [Proposal(invoice.id, debit.id, "linked", found)]
    chosen = strong or candidates
    return [Proposal(invoice.id, d.id, "suggested", f) for d, f in chosen]

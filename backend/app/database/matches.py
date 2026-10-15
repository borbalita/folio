"""Invoice–transaction matches: running the rules, and the owner confirming or undoing them."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update

from app.database.engine import get_session
from app.database.models.email.mailbox import Mailbox
from app.database.models.email.message import EmailMessage
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.database.models.finance.invoice_match import (
    InvoiceMatch,
    MatchSource,
    MatchStatus,
)
from app.database.models.finance.transaction import Transaction
from app.finance.invoice_edits import mark_matched, set_paid
from app.finance.matching import Debit, InvoiceFacts, Proposal, propose

Pair = tuple[uuid.UUID, uuid.UUID]


def apply_proposals(
    row: Invoice,
    proposals: list[Proposal],
    existing: dict[Pair, InvoiceMatch],
    *,
    add: Callable[[InvoiceMatch], None],
    remove: Callable[[InvoiceMatch], None],
    now: datetime,
) -> tuple[int, int]:
    """Write one invoice's proposals onto its match rows; returns (linked, new suggestions).

    A link drops the invoice's other open suggestions; rejected rows are kept so the
    rules never propose those pairs again.
    """
    linked = suggested = 0
    for proposal in proposals:
        pair = (proposal.invoice_id, proposal.transaction_id)
        match = existing.get(pair)
        if match is None:
            match = InvoiceMatch(
                invoice_id=proposal.invoice_id,
                transaction_id=proposal.transaction_id,
                source=MatchSource.AUTO,
            )
            add(match)
            existing[pair] = match
            suggested += proposal.status == MatchStatus.SUGGESTED
        match.status = proposal.status
        match.signals = list(proposal.signals)
        if proposal.status == MatchStatus.LINKED:
            mark_matched(row, now=now)
            linked += 1
            for other_pair, other in list(existing.items()):
                if (
                    other_pair[0] == row.id
                    and other is not match
                    and other.status == MatchStatus.SUGGESTED
                ):
                    remove(other)
                    del existing[other_pair]
    return linked, suggested


def _facts(row: Invoice, sent_at: datetime) -> InvoiceFacts:
    return InvoiceFacts(
        id=row.id,
        amount=row.amount,
        currency=row.currency,
        iban=row.iban,
        invoice_number=row.invoice_number,
        reference=row.reference,
        payee=row.payee,
        start=row.invoice_date or sent_at.date(),
    )


def _debit(tx: Transaction) -> Debit:
    return Debit(
        id=tx.id,
        booking_date=tx.booking_date,
        amount=-tx.amount,
        currency=tx.currency,
        counterparty_iban=tx.counterparty_iban,
        counterparty_name=tx.counterparty_name,
        remittance=tx.remittance,
    )


def match_for_user(user_id: uuid.UUID, now: datetime | None = None) -> dict[str, int]:
    """Match the user's open invoices against the debits in their connected accounts."""
    now = now or datetime.now(UTC)
    counts = {"linked": 0, "suggested": 0}
    with get_session() as session:
        invoices = session.execute(
            select(Invoice, EmailMessage.sent_at)
            .join(EmailMessage, EmailMessage.id == Invoice.email_id)
            .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
            .where(
                Mailbox.user_id == user_id,
                Invoice.status == InvoiceStatus.OPEN,
                Invoice.amount.is_not(None),
            )
        ).all()
        if not invoices:
            return counts
        facts = [(row, _facts(row, sent_at)) for row, sent_at in invoices]
        since = min(fact.start for _, fact in facts)
        debits = [
            _debit(tx)
            for tx in session.scalars(
                select(Transaction)
                .join(BankAccount, BankAccount.id == Transaction.account_id)
                .join(BankConnection, BankConnection.id == BankAccount.connection_id)
                .where(
                    BankConnection.user_id == user_id,
                    Transaction.amount < 0,
                    Transaction.booking_date >= since,
                )
            )
        ]
        invoice_ids = [row.id for row, _ in facts]
        debit_ids = [d.id for d in debits]
        rows = session.scalars(
            select(InvoiceMatch).where(
                InvoiceMatch.invoice_id.in_(invoice_ids)
                | (
                    (InvoiceMatch.status == MatchStatus.LINKED)
                    & InvoiceMatch.transaction_id.in_(debit_ids)
                )
            )
        ).all()
        existing = {(m.invoice_id, m.transaction_id): m for m in rows}
        taken = {m.transaction_id for m in rows if m.status == MatchStatus.LINKED}
        for row, fact in facts:
            rejected = {
                tx_id
                for (inv_id, tx_id), m in existing.items()
                if inv_id == row.id and m.status == MatchStatus.REJECTED
            }
            proposals = propose(fact, debits, rejected=rejected, taken=taken)
            linked, suggested = apply_proposals(
                row, proposals, existing, add=session.add, remove=session.delete, now=now
            )
            counts["linked"] += linked
            counts["suggested"] += suggested
            taken.update(p.transaction_id for p in proposals if p.status == "linked")
        session.commit()
    return counts


def _owned_match(session, match_id: uuid.UUID, mailbox_ids: list[uuid.UUID]):
    row = session.execute(
        select(InvoiceMatch, Invoice, EmailMessage.mailbox_id)
        .join(Invoice, Invoice.id == InvoiceMatch.invoice_id)
        .join(EmailMessage, EmailMessage.id == Invoice.email_id)
        .where(InvoiceMatch.id == match_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match not found")
    if row.mailbox_id not in mailbox_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return row.InvoiceMatch, row.Invoice


def confirm(match_id: uuid.UUID, mailbox_ids: list[uuid.UUID]) -> uuid.UUID:
    """The owner says this transaction paid the invoice. Returns the invoice id."""
    with get_session() as session:
        match, invoice = _owned_match(session, match_id, mailbox_ids)
        if match.status == MatchStatus.REJECTED:
            raise HTTPException(status.HTTP_409_CONFLICT, "This match was rejected.")
        # Another invoice already holds this payment, or this invoice another payment.
        taken = session.execute(
            select(InvoiceMatch.id).where(
                InvoiceMatch.status == MatchStatus.LINKED,
                InvoiceMatch.id != match.id,
                (InvoiceMatch.invoice_id == match.invoice_id)
                | (InvoiceMatch.transaction_id == match.transaction_id),
            )
        ).first()
        if taken is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "The invoice or the payment is already linked."
            )
        match.status = MatchStatus.LINKED
        match.source = MatchSource.OWNER
        mark_matched(invoice, now=datetime.now(UTC))
        session.execute(
            delete(InvoiceMatch).where(
                InvoiceMatch.status == MatchStatus.SUGGESTED,
                InvoiceMatch.id != match.id,
                (InvoiceMatch.invoice_id == match.invoice_id)
                | (InvoiceMatch.transaction_id == match.transaction_id),
            )
        )
        session.commit()
        return invoice.id


def reject(match_id: uuid.UUID, mailbox_ids: list[uuid.UUID]) -> uuid.UUID:
    """Not this payment: never propose the pair again; a linked invoice becomes open."""
    with get_session() as session:
        match, invoice = _owned_match(session, match_id, mailbox_ids)
        if match.status == MatchStatus.LINKED:
            set_paid(invoice, paid=False, now=datetime.now(UTC))
        match.status = MatchStatus.REJECTED
        session.commit()
        return invoice.id


def reject_links(session, invoice_ids: list[uuid.UUID]) -> None:
    """After the owner un-marks invoices by hand, matching must not link them again."""
    session.execute(
        update(InvoiceMatch)
        .where(
            InvoiceMatch.invoice_id.in_(invoice_ids),
            InvoiceMatch.status == MatchStatus.LINKED,
        )
        .values(status=MatchStatus.REJECTED)
    )


def for_invoices(session, invoice_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Each invoice's linked payment and open suggestions, for the invoice payloads."""
    result: dict[uuid.UUID, dict[str, Any]] = {
        invoice_id: {"match": None, "suggestions": []} for invoice_id in invoice_ids
    }
    if not invoice_ids:
        return result
    rows = session.execute(
        select(InvoiceMatch, Transaction, BankConnection.bank)
        .join(Transaction, Transaction.id == InvoiceMatch.transaction_id)
        .join(BankAccount, BankAccount.id == Transaction.account_id)
        .join(BankConnection, BankConnection.id == BankAccount.connection_id)
        .where(
            InvoiceMatch.invoice_id.in_(invoice_ids),
            InvoiceMatch.status != MatchStatus.REJECTED,
        )
        .order_by(Transaction.booking_date)
    ).all()
    for match, tx, bank in rows:
        item = {
            "id": str(match.id),
            "source": match.source,
            "signals": list(match.signals or []),
            "transaction": {
                "id": str(tx.id),
                "date": tx.booking_date.isoformat(),
                "bank": bank,
                "counterparty": tx.counterparty_name,
                "amount": str(tx.amount),
                "currency": tx.currency,
            },
        }
        if match.status == MatchStatus.LINKED:
            result[match.invoice_id]["match"] = item
        else:
            result[match.invoice_id]["suggestions"].append(item)
    return result

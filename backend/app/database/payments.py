"""Payment drafts: prepare, approve (with the QR code), cancel, and complete on a match."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update

from app.database.engine import get_session
from app.database.models.email.message import EmailMessage
from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.database.models.finance.payment_draft import (
    OPEN_STATUSES,
    DraftStatus,
    PaymentDraft,
)
from app.finance.epc import epc_payload, qr_svg_data_uri
from app.finance.invoice_edits import apply_edit
from app.finance.payments import DraftValues, approve_refusal, draft_values, skip_reason

# An approved payment shows its invoice as pending until the debit arrives, for at
# most this long: a transfer takes a business day, plus a weekend or holiday.
PENDING_DAYS = 5

REFUSALS = {
    "not_open": "The invoice is no longer open; it may have been paid meanwhile.",
    "invalid_iban": "The invoice's IBAN is not valid.",
    "iban_changed": "The invoice's IBAN changed since this payment was prepared.",
    "amount_changed": "The invoice's amount changed since this payment was prepared.",
}

INCOMPLETE = {
    "missing_payee": "a payee",
    "missing_iban": "an IBAN",
    "invalid_iban": "a valid IBAN",
    "missing_amount": "an amount",
    "amount_not_positive": "an amount above zero",
}


def _draft(row: PaymentDraft, invoice: Invoice) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "invoiceId": str(row.invoice_id),
        "emailId": str(invoice.email_id),
        "attachmentId": str(invoice.attachment_id) if invoice.attachment_id else None,
        "payee": row.payee,
        "iban": row.iban,
        "bic": row.bic,
        "amount": str(row.amount),
        "currency": row.currency,
        "reference": row.reference,
        "status": row.status,
    }


def create_drafts(
    invoice_ids: list[uuid.UUID], mailbox_ids: list[uuid.UUID]
) -> dict[str, Any]:
    """A fresh draft per open invoice, replacing an unapproved one; the rest are skipped.

    No paying account is chosen: the QR code carries none, and the banking app that scans
    it pays from its own account.
    """
    with get_session() as session:
        rows = session.execute(
            select(Invoice, EmailMessage.mailbox_id)
            .join(EmailMessage, EmailMessage.id == Invoice.email_id)
            .where(Invoice.id.in_(invoice_ids))
        ).all()
        by_id = {row.Invoice.id: row for row in rows}
        if any(i not in by_id for i in invoice_ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
        if any(row.mailbox_id not in mailbox_ids for row in rows):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        invoices = [by_id[i].Invoice for i in invoice_ids]
        # An approved payment may already have been sent from the banking app; a second
        # QR code for the same invoice invites paying twice. The owner cancels it first.
        approved = set(
            session.scalars(
                select(PaymentDraft.invoice_id).where(
                    PaymentDraft.invoice_id.in_(invoice_ids),
                    PaymentDraft.status == DraftStatus.APPROVED,
                )
            )
        )
        reasons = {
            inv.id: skip_reason(inv) or ("already_approved" if inv.id in approved else None)
            for inv in invoices
        }
        payable = [inv for inv in invoices if reasons[inv.id] is None]
        skipped = [
            {"invoiceId": str(inv.id), "reason": reasons[inv.id]}
            for inv in invoices
            if reasons[inv.id] is not None
        ]
        if payable:
            session.execute(
                update(PaymentDraft)
                .where(
                    PaymentDraft.invoice_id.in_([inv.id for inv in payable]),
                    PaymentDraft.status == DraftStatus.DRAFT,
                )
                .values(status=DraftStatus.CANCELLED)
            )
        drafts = []
        for inv in payable:
            values = draft_values(inv)
            draft = PaymentDraft(
                id=uuid.uuid4(),
                invoice_id=inv.id,
                payee=values.payee,
                iban=values.iban,
                bic=values.bic,
                amount=values.amount,
                currency=values.currency,
                reference=values.reference,
                status=DraftStatus.DRAFT,
            )
            session.add(draft)
            drafts.append(_draft(draft, inv))
        session.commit()
        return {"drafts": drafts, "skipped": skipped}


def _owned_draft(session, draft_id: uuid.UUID, mailbox_ids: list[uuid.UUID]):
    row = session.execute(
        select(PaymentDraft, Invoice, EmailMessage.mailbox_id)
        .join(Invoice, Invoice.id == PaymentDraft.invoice_id)
        .join(EmailMessage, EmailMessage.id == Invoice.email_id)
        .where(PaymentDraft.id == draft_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if row.mailbox_id not in mailbox_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return row


def get_drafts(draft_ids: list[uuid.UUID], mailbox_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    with get_session() as session:
        return [
            _draft(row.PaymentDraft, row.Invoice)
            for row in (_owned_draft(session, i, mailbox_ids) for i in draft_ids)
        ]


def approve(
    draft_id: uuid.UUID, mailbox_ids: list[uuid.UUID], changes: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Save the owner's corrections, re-check the invoice, then hand out the QR code.

    Corrections go to the invoice as owner edits, not only to the draft: matching the
    bank debit later reads the invoice's IBAN and amount.
    """
    with get_session() as session:
        row = _owned_draft(session, draft_id, mailbox_ids)
        draft, invoice = row.PaymentDraft, row.Invoice
        if draft.status not in OPEN_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, f"This payment is {draft.status}.")
        if changes:
            if invoice.status != InvoiceStatus.OPEN:
                raise HTTPException(status.HTTP_409_CONFLICT, REFUSALS["not_open"])
            apply_edit(invoice, changes)
            if invoice.status != InvoiceStatus.OPEN:
                needs = [INCOMPLETE[i] for i in invoice.issues if i in INCOMPLETE]
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"The payment needs {' and '.join(needs or ['complete details'])}.",
                )
            # Only the corrected fields: a value changed elsewhere since the draft was
            # made must still be refused below, not paid unseen.
            values = draft_values(invoice)
            for name in changes:
                setattr(draft, name, getattr(values, name))
        frozen = DraftValues(
            payee=draft.payee,
            iban=draft.iban,
            bic=draft.bic,
            amount=draft.amount,
            currency=draft.currency,
            reference=draft.reference,
        )
        refusal = approve_refusal(invoice, frozen)
        if refusal is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, REFUSALS[refusal])
        payload = epc_payload(
            name=draft.payee,
            iban=draft.iban,
            bic=draft.bic,
            amount=draft.amount,
            remittance=draft.reference,
        )
        draft.status = DraftStatus.APPROVED
        draft.approved_at = datetime.now(UTC)
        session.commit()
        return {
            **_draft(draft, invoice),
            "payload": payload,
            "qr": qr_svg_data_uri(payload),
        }


def cancel(draft_id: uuid.UUID, mailbox_ids: list[uuid.UUID]) -> dict[str, Any]:
    with get_session() as session:
        row = _owned_draft(session, draft_id, mailbox_ids)
        if row.PaymentDraft.status in OPEN_STATUSES:
            row.PaymentDraft.status = DraftStatus.CANCELLED
            session.commit()
        return _draft(row.PaymentDraft, row.Invoice)


def complete_for_invoices(session, invoice_ids: list[uuid.UUID]) -> None:
    """A linked bank payment means the approved transfer went through."""
    if not invoice_ids:
        return
    session.execute(
        update(PaymentDraft)
        .where(
            PaymentDraft.invoice_id.in_(invoice_ids),
            PaymentDraft.status == DraftStatus.APPROVED,
        )
        .values(status=DraftStatus.COMPLETED)
    )


def is_payment_pending(status: str, approved_at: datetime | None, now: datetime) -> bool:
    """Approved within the last PENDING_DAYS; after that the invoice shows open again."""
    return (
        status == DraftStatus.APPROVED
        and approved_at is not None
        and approved_at >= now - timedelta(days=PENDING_DAYS)
    )


def pending_invoice_ids(
    session, invoice_ids: list[uuid.UUID], *, now: datetime | None = None
) -> set[uuid.UUID]:
    """The invoices among these whose payment is approved and still expected."""
    if not invoice_ids:
        return set()
    now = now or datetime.now(UTC)
    rows = session.execute(
        select(PaymentDraft.invoice_id, PaymentDraft.status, PaymentDraft.approved_at).where(
            PaymentDraft.invoice_id.in_(invoice_ids),
            PaymentDraft.status == DraftStatus.APPROVED,
        )
    ).all()
    return {
        row.invoice_id
        for row in rows
        if is_payment_pending(row.status, row.approved_at, now)
    }

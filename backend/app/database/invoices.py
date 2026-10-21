"""Invoices, their emails and PDF attachments, scoped to the caller's mailboxes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select

from app.database import matches
from app.database.engine import get_session
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailMessage
from app.database.models.finance.invoice import Invoice
from app.finance.invoice_edits import apply_edit, set_paid


@dataclass(frozen=True, slots=True)
class AttachmentFile:
    filename: str
    content_type: str
    content: bytes


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _summary(email: EmailMessage) -> dict[str, Any]:
    return {
        "id": str(email.id),
        "from": email.from_address,
        "subject": email.subject,
        "sentAt": email.sent_at.isoformat(),
    }


def serialize_invoice(row: Invoice) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "emailId": str(row.email_id),
        "attachmentId": str(row.attachment_id) if row.attachment_id else None,
        "payee": row.payee,
        "iban": row.iban,
        "bic": row.bic,
        "amount": str(row.amount) if row.amount is not None else None,
        "currency": row.currency,
        "invoiceNumber": row.invoice_number,
        "reference": row.reference,
        "invoiceDate": row.invoice_date.isoformat() if row.invoice_date else None,
        "dueDate": row.due_date.isoformat() if row.due_date else None,
        "status": row.status,
        "issues": list(row.issues or []),
        "paidAt": row.paid_at.isoformat() if row.paid_at else None,
        "paidBy": row.paid_by,
    }


def list_invoices(mailbox_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Every invoice in these mailboxes with its email, newest email first."""
    with get_session() as session:
        rows = session.execute(
            select(Invoice, EmailMessage)
            .join(EmailMessage, EmailMessage.id == Invoice.email_id)
            .where(EmailMessage.mailbox_id.in_(mailbox_ids))
            .order_by(EmailMessage.sent_at.desc(), Invoice.position)
        ).all()
        found = matches.for_invoices(session, [row.Invoice.id for row in rows])
        return [
            {
                **serialize_invoice(row.Invoice),
                **found[row.Invoice.id],
                "email": _summary(row.EmailMessage),
            }
            for row in rows
        ]


def get_invoice(email_id: uuid.UUID, mailbox_ids: list[uuid.UUID]) -> dict[str, Any]:
    """One email with its body and attachment metadata. PDF bytes are fetched separately."""
    with get_session() as session:
        email = session.get(EmailMessage, email_id)
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email not found"
            )
        if email.mailbox_id not in mailbox_ids:
            raise _forbidden()
        rows = session.execute(
            select(
                EmailAttachment.id,
                EmailAttachment.filename,
                EmailAttachment.size_bytes,
                EmailAttachment.skipped_reason,
            )
            .where(EmailAttachment.email_id == email_id)
            .order_by(EmailAttachment.filename)
        )
        attachments = [
            {
                "id": str(row.id),
                "filename": row.filename,
                "sizeBytes": row.size_bytes,
                "skippedReason": row.skipped_reason,
            }
            for row in rows
        ]
        rows = session.scalars(
            select(Invoice)
            .where(Invoice.email_id == email_id)
            .order_by(Invoice.position)
        ).all()
        found = matches.for_invoices(session, [row.id for row in rows])
        return {
            **_summary(email),
            "body": email.body,
            "attachments": attachments,
            "invoices": [{**serialize_invoice(row), **found[row.id]} for row in rows],
        }


def _owned_invoices(
    session, invoice_ids: list[uuid.UUID], mailbox_ids: list[uuid.UUID]
) -> list[Invoice]:
    """The invoices in the given order; 404 if any is unknown, 403 if any is someone else's."""
    rows = session.execute(
        select(Invoice, EmailMessage.mailbox_id)
        .join(EmailMessage, EmailMessage.id == Invoice.email_id)
        .where(Invoice.id.in_(invoice_ids))
    ).all()
    by_id = {row.Invoice.id: row for row in rows}
    if any(invoice_id not in by_id for invoice_id in invoice_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    if any(row.mailbox_id not in mailbox_ids for row in rows):
        raise _forbidden()
    return [by_id[invoice_id].Invoice for invoice_id in invoice_ids]


def update_invoice(
    invoice_id: uuid.UUID, changes: dict[str, Any], mailbox_ids: list[uuid.UUID]
) -> dict[str, Any]:
    with get_session() as session:
        [row] = _owned_invoices(session, [invoice_id], mailbox_ids)
        apply_edit(row, changes)
        session.commit()
        return serialize_invoice(row)


def get_invoice_item(
    invoice_id: uuid.UUID, mailbox_ids: list[uuid.UUID]
) -> dict[str, Any]:
    """One invoice with its match and suggestions."""
    with get_session() as session:
        [row] = _owned_invoices(session, [invoice_id], mailbox_ids)
        return {**serialize_invoice(row), **matches.for_invoices(session, [row.id])[row.id]}


def set_invoices_paid(
    invoice_ids: list[uuid.UUID], paid: bool, mailbox_ids: list[uuid.UUID]
) -> list[dict[str, Any]]:
    """Mark all or none: one unknown or foreign id changes nothing."""
    with get_session() as session:
        rows = _owned_invoices(session, invoice_ids, mailbox_ids)
        now = datetime.now(UTC)
        for row in rows:
            set_paid(row, paid=paid, now=now)
        if not paid:
            matches.reject_links(session, invoice_ids)
        session.commit()
        found = matches.for_invoices(session, invoice_ids)
        return [{**serialize_invoice(row), **found[row.id]} for row in rows]


def get_attachment_file(
    attachment_id: uuid.UUID, mailbox_ids: list[uuid.UUID]
) -> AttachmentFile:
    with get_session() as session:
        row = session.execute(
            select(
                EmailAttachment.filename,
                EmailAttachment.content_type,
                EmailAttachment.content,
                EmailMessage.mailbox_id,
            )
            .join(EmailMessage, EmailMessage.id == EmailAttachment.email_id)
            .where(EmailAttachment.id == attachment_id)
        ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found"
        )
    if row.mailbox_id not in mailbox_ids:
        raise _forbidden()
    if row.content is None:
        # Skipped at ingest (over the size cap); only its metadata exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not stored"
        )
    return AttachmentFile(
        filename=row.filename, content_type=row.content_type, content=row.content
    )

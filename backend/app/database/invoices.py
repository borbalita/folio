"""Invoice emails and their PDF attachments, scoped to the caller's mailboxes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select

from app.database.engine import get_session
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel, EmailMessage


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


def list_invoices(mailbox_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Emails labeled `invoice` in these mailboxes, newest first."""
    with get_session() as session:
        emails = session.scalars(
            select(EmailMessage)
            .where(
                EmailMessage.mailbox_id.in_(mailbox_ids),
                EmailMessage.label == EmailLabel.INVOICE.value,
            )
            .order_by(EmailMessage.sent_at.desc())
        )
        return [_summary(email) for email in emails]


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
        return {**_summary(email), "body": email.body, "attachments": attachments}


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

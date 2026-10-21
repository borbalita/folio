"""A new demo invoice, built from the catalogue and sent through the real email pipeline."""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from langfuse import propagate_attributes
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_session
from app.database.invoices import serialize_invoice
from app.database.matches import match_for_user
from app.database.models.email.message import EmailMessage
from app.database.models.finance.invoice import Invoice
from app.demo.accounts import demo_address, ensure_demo_accounts
from app.demo.emails import InvoiceKind, draw_invoice, invoice_message
from ingest.email.pipeline import ingest_messages
from ingest.email.pipeline import open_session as open_ingest_session

RequestedKind = Literal["normal", "already_paid", "online_only", "random"]
KINDS: tuple[InvoiceKind, ...] = ("normal", "already_paid", "online_only")
MODEL_ERROR = "The models could not read this invoice; it is stored as needs info."


def resolve_kind(kind: RequestedKind, rng: random.Random) -> InvoiceKind:
    return rng.choice(KINDS) if kind == "random" else kind


def send_invoice(
    user_id: uuid.UUID,
    kind: RequestedKind,
    *,
    rng: random.Random | None = None,
    now: datetime | None = None,
    open_session: Callable[[], Session] = open_ingest_session,
    match: Callable[[uuid.UUID], dict[str, int]] = match_for_user,
    **pipeline: Any,
) -> dict[str, Any]:
    """Build one invoice email, ingest it into the demo mailbox, match, and report what was stored.

    `pipeline` passes model fakes (embed, classifier, invoice_extract, invoice_check) to
    ingest_messages in tests; in the app the real models run.
    """
    rng = rng or random.Random()
    now = now or datetime.now(UTC)
    built = draw_invoice(rng, resolve_kind(kind, rng), now.date())
    message = invoice_message(
        built, rng=rng, to_address=demo_address(user_id), sent_at=now
    )
    session = open_session()
    try:
        mailbox_id = ensure_demo_accounts(session, user_id).mailbox_id
        session.commit()
        with propagate_attributes(tags=["demo"]):
            summary = ingest_messages(session, mailbox_id, [message], **pipeline)
    finally:
        session.close()
    match(user_id)
    return {
        "sent": {
            "kind": built.kind,
            "vendor": built.vendor.name,
            "number": built.number,
            "amount": str(built.amount),
        },
        "invoices": _stored_invoices(mailbox_id, message.message_id),
        "failures": summary.invoice_failures,
        "error": MODEL_ERROR if summary.invoice_failures else None,
    }


def _stored_invoices(
    mailbox_id: uuid.UUID, message_id: str | None
) -> list[dict[str, Any]]:
    """The invoices stored for this email, read after matching so paid ones show as paid."""
    with get_session() as session:
        rows = session.scalars(
            select(Invoice)
            .join(EmailMessage, EmailMessage.id == Invoice.email_id)
            .where(
                EmailMessage.mailbox_id == mailbox_id,
                EmailMessage.message_id == message_id,
            )
            .order_by(Invoice.position)
        )
        return [serialize_invoice(row) for row in rows]

"""Simulated bank booking: an approved demo payment leaves the demo account, then matching runs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database.engine import get_session
from app.database.matches import match_for_user
from app.database.models.email.mailbox import Mailbox
from app.database.models.email.message import EmailMessage
from app.database.models.finance.invoice import Invoice
from app.database.models.finance.payment_draft import DraftStatus, PaymentDraft
from app.database.models.finance.transaction import Transaction
from app.demo.accounts import ensure_demo_accounts


def booking_transaction(
    draft: PaymentDraft, account_id: uuid.UUID, today: date
) -> Transaction:
    """The debit the bank would show for this transfer, booked today."""
    return Transaction(
        account_id=account_id,
        booking_date=today,
        amount=-draft.amount,
        currency=draft.currency,
        counterparty_name=draft.payee,
        counterparty_iban=draft.iban,
        remittance=draft.reference or "",
        bank_code="demo",
        entry_reference=None,
        # One booking per payment: the account's unique dedup key refuses a second.
        dedup_key=f"demo-booking:{draft.id}",
        raw={"demo_booking": str(draft.id)},
    )


def _owned_drafts(user_id: uuid.UUID):
    return (
        select(PaymentDraft)
        .join(Invoice, Invoice.id == PaymentDraft.invoice_id)
        .join(EmailMessage, EmailMessage.id == Invoice.email_id)
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .where(Mailbox.user_id == user_id)
    )


def approved_payments(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The user's approved payments, newest approval first."""
    with get_session() as session:
        drafts = session.scalars(
            _owned_drafts(user_id)
            .where(PaymentDraft.status == DraftStatus.APPROVED)
            .order_by(PaymentDraft.approved_at.desc())
        )
        return [
            {
                "id": str(draft.id),
                "invoiceId": str(draft.invoice_id),
                "payee": draft.payee,
                "amount": str(draft.amount),
                "currency": draft.currency,
                "reference": draft.reference,
                "approvedAt": draft.approved_at.isoformat()
                if draft.approved_at
                else None,
            }
            for draft in drafts
        ]


def book(
    user_id: uuid.UUID, draft_id: uuid.UUID, today: date | None = None
) -> dict[str, Any]:
    """Book an approved payment once and run matching; anything else changes nothing."""
    today = today or datetime.now(ZoneInfo(settings.email_timezone)).date()
    with get_session() as session:
        draft = session.scalar(
            _owned_drafts(user_id).where(PaymentDraft.id == draft_id)
        )
        if draft is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
        booked = draft.status == DraftStatus.APPROVED and _insert_booking(
            session, draft, ensure_demo_accounts(session, user_id).account_id, today
        )
        if booked:
            session.commit()
    if booked:
        match_for_user(user_id)
    payment_status, invoice_status = _statuses(draft_id)
    return {
        "booked": booked,
        "paymentStatus": payment_status,
        "invoiceStatus": invoice_status,
    }


def _insert_booking(
    session, draft: PaymentDraft, account_id: uuid.UUID, today: date
) -> bool:
    """False when this payment was booked before (the dedup key already exists)."""
    tx = booking_transaction(draft, account_id, today)
    values = {
        column.name: getattr(tx, column.key)
        for column in Transaction.__table__.columns
        if column.name not in ("id", "created_at")
    }
    inserted = session.execute(
        insert(Transaction)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["account_id", "dedup_key"])
        .returning(Transaction.id)
    ).scalar_one_or_none()
    return inserted is not None


def _statuses(draft_id: uuid.UUID) -> tuple[str, str]:
    with get_session() as session:
        row = session.execute(
            select(PaymentDraft.status, Invoice.status)
            .join(Invoice, Invoice.id == PaymentDraft.invoice_id)
            .where(PaymentDraft.id == draft_id)
        ).one()
        return row[0], row[1]

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class DraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


OPEN_STATUSES = (DraftStatus.DRAFT, DraftStatus.APPROVED)


class PaymentDraft(Base):
    """A payment prepared for an invoice, with the values frozen when it was made."""

    __tablename__ = "payment_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    payee: Mapped[str] = mapped_column(Text, nullable=False)
    iban: Mapped[str] = mapped_column(Text, nullable=False)
    bic: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in DraftStatus) + ")",
            name="ck_payment_drafts_status",
        ),
        # At most one draft in progress per invoice.
        Index(
            "uq_payment_drafts_open_invoice",
            "invoice_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'approved')"),
        ),
    )

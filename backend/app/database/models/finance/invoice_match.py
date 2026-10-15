import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class MatchStatus(StrEnum):
    LINKED = "linked"
    SUGGESTED = "suggested"
    REJECTED = "rejected"


class MatchSource(StrEnum):
    AUTO = "auto"
    OWNER = "owner"


class InvoiceMatch(Base):
    """A transaction proposed as, or confirmed as, the payment of an invoice."""

    __tablename__ = "invoice_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # Which of amount, iban, reference and name matched.
    signals: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
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
        UniqueConstraint(
            "invoice_id", "transaction_id", name="uq_invoice_matches_invoice_id_transaction_id"
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in MatchStatus) + ")",
            name="ck_invoice_matches_status",
        ),
        CheckConstraint(
            "source IN (" + ", ".join(f"'{s.value}'" for s in MatchSource) + ")",
            name="ck_invoice_matches_source",
        ),
        # One payment per invoice, and one invoice per payment.
        Index(
            "uq_invoice_matches_linked_invoice",
            "invoice_id",
            unique=True,
            postgresql_where=text("status = 'linked'"),
        ),
        Index(
            "uq_invoice_matches_linked_transaction",
            "transaction_id",
            unique=True,
            postgresql_where=text("status = 'linked'"),
        ),
    )

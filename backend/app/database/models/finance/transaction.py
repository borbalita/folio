import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Signed: negative for money leaving the account.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_iban: Mapped[str | None] = mapped_column(Text, nullable=True)
    remittance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bank_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id", "dedup_key", name="uq_transactions_account_id_dedup_key"
        ),
        Index("ix_transactions_account_id_booking_date", "account_id", "booking_date"),
    )

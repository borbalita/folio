import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    uid: Mapped[str] = mapped_column(Text, nullable=False)
    identification_hash: Mapped[str] = mapped_column(Text, nullable=False)
    iban: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "identification_hash",
            name="uq_bank_accounts_connection_id_identification_hash",
        ),
    )

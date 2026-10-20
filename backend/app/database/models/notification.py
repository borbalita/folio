import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class NotificationKind(StrEnum):
    INVOICE_NEW = "invoice_new"
    INVOICE_DUE = "invoice_due"
    NEWS_BIG = "news_big"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class Notification(Base):
    """One message to the owner, recorded once per event; the key makes it once."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Error type only; never the message or Telegram's answer.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k.value}'" for k in NotificationKind) + ")",
            name="ck_notifications_kind",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in NotificationStatus) + ")",
            name="ck_notifications_status",
        ),
        Index("ix_notifications_status_created_at", "status", "created_at"),
    )

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class EmailLabel(StrEnum):
    NEEDS_REPLY = "needs_reply"
    PROMOTIONAL = "promotional"
    NEWSLETTER = "newsletter"
    INVOICE = "invoice"
    OTHER = "other"
    AI_NEWSLETTER = "ai_newsletter"


class NewsletterSource(StrEnum):
    TLDR = "tldr"
    ALPHA_SIGNAL = "alpha_signal"


def _in_list(column: str, members: type[StrEnum]) -> str:
    listed = ", ".join(f"'{member.value}'" for member in members)
    return f"{column} IN ({listed})"


class EmailMessage(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    from_address: Mapped[str] = mapped_column(Text, nullable=False)
    to_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=EmailLabel.OTHER.value
    )
    newsletter_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
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
            "mailbox_id", "message_id", name="uq_emails_mailbox_message_id"
        ),
        CheckConstraint(_in_list("label", EmailLabel), name="ck_emails_label"),
        CheckConstraint(
            f"newsletter_source IS NULL OR {_in_list('newsletter_source', NewsletterSource)}",
            name="ck_emails_newsletter_source",
        ),
        Index(
            "ix_emails_mailbox_label_sent_at",
            "mailbox_id",
            "label",
            desc("sent_at"),
        ),
        Index("ix_emails_from_address", "from_address"),
    )

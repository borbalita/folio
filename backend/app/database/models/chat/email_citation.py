import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class EmailCitation(Base):
    __tablename__ = "email_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    email_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_chunks.id", ondelete="CASCADE"),
        nullable=True,
    )
    news_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    citation_index: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(email_chunk_id IS NOT NULL) <> (news_item_id IS NOT NULL)",
            name="ck_email_citations_one_target",
        ),
        UniqueConstraint(
            "message_id", "citation_index", name="uq_email_citations_message_index"
        ),
        Index("ix_email_citations_message_id", "message_id"),
        Index("ix_email_citations_email_chunk_id", "email_chunk_id"),
        Index("ix_email_citations_news_item_id", "news_item_id"),
    )

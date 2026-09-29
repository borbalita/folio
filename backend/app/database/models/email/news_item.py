import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
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

from app.config import settings
from app.database.models.base import Base
from app.database.models.email.message import NewsletterSource


def _source_check() -> str:
    listed = ", ".join(f"'{member.value}'" for member in NewsletterSource)
    return f"source IN ({listed})"


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    edition_date: Mapped[date] = mapped_column(Date, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    blurb: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.openai_embedding_dimensions), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_stories.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("email_id", "position", name="uq_news_items_email_position"),
        CheckConstraint(_source_check(), name="ck_news_items_source"),
        Index("ix_news_items_email_id", "email_id"),
        Index("ix_news_items_story_id", "story_id"),
    )

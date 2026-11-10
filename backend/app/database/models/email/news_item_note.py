import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

ALERT_STATUSES = ("new", "update", "repeat")


class NewsItemNote(Base):
    """What the app wrote about one newsletter item.

    Keyed like the notification keys: an item's email and position survive re-embedding and
    story rebuilds, its id and story do not.
    """

    __tablename__ = "news_item_notes"

    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Null until classified (002/04).
    security: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alert_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("email_id", "position", name="pk_news_item_notes"),
        CheckConstraint(
            "alert_status IS NULL OR alert_status IN ("
            + ", ".join(f"'{status}'" for status in ALERT_STATUSES)
            + ")",
            name="ck_news_item_notes_alert_status",
        ),
    )

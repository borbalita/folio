import uuid
from datetime import date

from sqlalchemy import Boolean, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class NewsStory(Base):
    __tablename__ = "news_stories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    is_big: Mapped[bool] = mapped_column(Boolean, nullable=False)

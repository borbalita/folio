"""Mailbox lookups used to decide who has the email agent."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database.engine import get_session
from app.database.models.email.mailbox import Mailbox


def active_mailbox_ids(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of this user's active mailboxes. Later email queries stay inside this set."""
    with get_session() as session:
        return list(
            session.scalars(
                select(Mailbox.id).where(
                    Mailbox.user_id == user_id,
                    Mailbox.is_active.is_(True),
                )
            )
        )

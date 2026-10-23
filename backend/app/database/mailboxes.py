"""Mailbox lookups: which mailboxes the email agent, Finance and AI News may read."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database.engine import get_session
from app.database.models.email.mailbox import Mailbox


def active_mailbox_ids(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of this user's active mailboxes. Later email queries stay inside this set.

    The demo mailbox counts too: it holds the demo user's invented mail and belongs to no one else.
    """
    with get_session() as session:
        return list(
            session.scalars(
                select(Mailbox.id).where(
                    Mailbox.user_id == user_id,
                    Mailbox.is_active.is_(True),
                )
            )
        )


def invoice_mailbox_ids(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of every active mailbox of this user, demo included. Finance stays inside this set.

    Equal to active_mailbox_ids since 03-email 001; kept apart so one agent's scope can narrow
    without touching the others.
    """
    with get_session() as session:
        return list(
            session.scalars(
                select(Mailbox.id).where(
                    Mailbox.user_id == user_id,
                    Mailbox.is_active.is_(True),
                )
            )
        )


# Same scope as invoices today: the demo mailbox holds fixture newsletters too. Kept as its own
# name so News can narrow its scope without touching Finance.
news_mailbox_ids = invoice_mailbox_ids

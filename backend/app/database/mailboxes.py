"""Mailbox lookups: which mailboxes the email agent, Finance and AI News may read."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database.engine import get_session
from app.database.models.email.mailbox import Mailbox, MailboxProvider


def active_mailbox_ids(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of this user's active mailboxes. Later email queries stay inside this set.

    The demo mailbox holds fixture invoices only, so it never opens Email.
    """
    with get_session() as session:
        return list(
            session.scalars(
                select(Mailbox.id).where(
                    Mailbox.user_id == user_id,
                    Mailbox.is_active.is_(True),
                    Mailbox.provider != MailboxProvider.DEMO,
                )
            )
        )


def invoice_mailbox_ids(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of every active mailbox of this user, demo included. Finance stays inside this set."""
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

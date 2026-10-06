"""Fake users and mailboxes seeded into the eval database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.user import User


@dataclass(frozen=True, slots=True)
class FakeMailbox:
    id: uuid.UUID
    user_id: uuid.UUID
    address: str
    display_name: str
    is_active: bool


USER_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
USER_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")

USERS = {USER_A: "anna@example.com", USER_B: "ben@example.com"}

A_ACTIVE = FakeMailbox(
    id=uuid.UUID("00000000-0000-4000-8000-0000000000a1"),
    user_id=USER_A,
    address="anna@example.com",
    display_name="Anna",
    is_active=True,
)
A_INACTIVE = FakeMailbox(
    id=uuid.UUID("00000000-0000-4000-8000-0000000000a2"),
    user_id=USER_A,
    address="anna.old@example.com",
    display_name="Anna (old)",
    is_active=False,
)
B_ACTIVE = FakeMailbox(
    id=uuid.UUID("00000000-0000-4000-8000-0000000000b1"),
    user_id=USER_B,
    address="ben@example.com",
    display_name="Ben",
    is_active=True,
)

MAILBOXES = (A_ACTIVE, A_INACTIVE, B_ACTIVE)


def seed_users_and_mailboxes(session: Session) -> None:
    for user_id, email in USERS.items():
        session.add(User(id=user_id, email=email))
    session.flush()
    for mailbox in MAILBOXES:
        session.add(
            Mailbox(
                id=mailbox.id,
                user_id=mailbox.user_id,
                provider=MailboxProvider.GMAIL.value,
                address=mailbox.address,
                display_name=mailbox.display_name,
                is_active=mailbox.is_active,
            )
        )
    session.commit()

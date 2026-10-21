"""The demo user's mailbox and bank account, created on first use."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.bank_connections import DEMO_BANK
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection

DEMO_IDENTIFICATION = "demo"


def demo_address(user_id: uuid.UUID) -> str:
    return f"demo+{user_id}@folio.example"


@dataclass(frozen=True)
class DemoAccounts:
    mailbox_id: uuid.UUID
    account_id: uuid.UUID


def ensure_demo_accounts(session: Session, user_id: uuid.UUID) -> DemoAccounts:
    """Create what is missing and return the ids. The caller owns the transaction.

    Assumes the users row exists.
    """
    mailbox = session.scalar(
        select(Mailbox).where(
            Mailbox.user_id == user_id, Mailbox.provider == MailboxProvider.DEMO
        )
    )
    if mailbox is None:
        mailbox = Mailbox(
            user_id=user_id,
            provider=MailboxProvider.DEMO,
            address=demo_address(user_id),
            display_name="Demo",
        )
        session.add(mailbox)
    connection = session.scalar(
        select(BankConnection).where(
            BankConnection.user_id == user_id, BankConnection.bank == DEMO_BANK
        )
    )
    if connection is None:
        connection = BankConnection(
            user_id=user_id,
            bank=DEMO_BANK,
            session_id=DEMO_IDENTIFICATION,
            valid_until=datetime.now(UTC) + timedelta(days=3650),
        )
        session.add(connection)
    session.flush()
    account = session.scalar(
        select(BankAccount).where(
            BankAccount.connection_id == connection.id,
            BankAccount.identification_hash == DEMO_IDENTIFICATION,
        )
    )
    if account is None:
        account = BankAccount(
            connection_id=connection.id,
            uid=DEMO_IDENTIFICATION,
            identification_hash=DEMO_IDENTIFICATION,
            iban="DE89370400440532013000",
            name="Girokonto",
            currency="EUR",
        )
        session.add(account)
        session.flush()
    return DemoAccounts(mailbox_id=mailbox.id, account_id=account.id)

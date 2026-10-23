"""The demo user's mailbox and bank accounts, created on first use."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.bank_connections import DEMO_BANKS
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.demo.catalogue import demo_iban

DEMO_IDENTIFICATION = "demo"


@dataclass(frozen=True, slots=True)
class _DemoAccountSpec:
    bank: str
    key: str
    name: str
    iban: str | None


# In DEMO_BANKS order: a current account, a card account, and a wallet without an IBAN.
_ACCOUNTS = (
    _DemoAccountSpec(
        "Spreeufer Bank", "demo-girokonto", "Girokonto", "DE89370400440532013000"
    ),
    _DemoAccountSpec(
        "Kiez Direkt",
        "demo-alltag",
        "Alltagskonto",
        demo_iban("10070000", "0081500142"),
    ),
    _DemoAccountSpec("TalerPay", "demo-wallet", "TalerPay-Konto", None),
)
assert tuple(spec.bank for spec in _ACCOUNTS) == DEMO_BANKS


def demo_address(user_id: uuid.UUID) -> str:
    return f"demo+{user_id}@folio.example"


@dataclass(frozen=True)
class DemoAccounts:
    mailbox_id: uuid.UUID
    # The Girokonto: salary, rent, transfers, and the presenter's bookings.
    account_id: uuid.UUID
    card_account_id: uuid.UUID
    wallet_account_id: uuid.UUID

    @property
    def account_ids(self) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        return (self.account_id, self.card_account_id, self.wallet_account_id)


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
    account_ids = [_ensure_account(session, user_id, spec) for spec in _ACCOUNTS]
    session.flush()
    return DemoAccounts(mailbox.id, *account_ids)


def _ensure_account(
    session: Session, user_id: uuid.UUID, spec: _DemoAccountSpec
) -> uuid.UUID:
    connection = session.scalar(
        select(BankConnection).where(
            BankConnection.user_id == user_id, BankConnection.bank == spec.bank
        )
    )
    if connection is None:
        connection = BankConnection(
            user_id=user_id,
            bank=spec.bank,
            session_id=DEMO_IDENTIFICATION,
            valid_until=datetime.now(UTC) + timedelta(days=3650),
        )
        session.add(connection)
        session.flush()
    account = session.scalar(
        select(BankAccount).where(
            BankAccount.connection_id == connection.id,
            BankAccount.identification_hash == spec.key,
        )
    )
    if account is None:
        account = BankAccount(
            connection_id=connection.id,
            uid=spec.key,
            identification_hash=spec.key,
            iban=spec.iban,
            name=spec.name,
            currency="EUR",
        )
        session.add(account)
        session.flush()
    return account.id

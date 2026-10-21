"""The demo reset against a real Postgres: the local eval database (see evals/README.md).

Run: uv run --env-file .env.eval pytest -m integration tests/demo/test_demo_reset_integration.py
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_engine
from app.database.models.chat.thread import ChatThread
from app.database.models.email.mailbox import Mailbox
from app.database.models.email.message import EmailMessage
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.database.models.finance.payment_draft import DraftStatus, PaymentDraft
from app.database.models.finance.transaction import Transaction
from app.database.models.user import User
from app.demo.accounts import ensure_demo_accounts
from app.demo.reset import reset_demo
from evals.guard import require_local_database

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 21)
OWNER = uuid.uuid4()
DEMO = uuid.uuid4()


@pytest.fixture
def session() -> Iterator[Session]:
    """A session whose commits stay inside one outer transaction, rolled back at the end."""
    require_local_database(settings.database_url)
    with get_engine().connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def _email(mailbox_id: uuid.UUID, message_id: str) -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        mailbox_id=mailbox_id,
        message_id=message_id,
        folder="INBOX",
        subject="Rechnung",
        from_address="billing@shop.example",
        to_addresses=[],
        sent_at=datetime(2026, 10, 1, 9, tzinfo=UTC),
        body="Rechnung anbei.",
        label="invoice",
        content_hash="x",
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.openai_embedding_dimensions,
    )


def _owner_rows(session: Session) -> dict[str, uuid.UUID]:
    mailbox = Mailbox(
        id=uuid.uuid4(), user_id=OWNER, provider="yahoo", address=f"{OWNER}@x.example",
        display_name="Owner",
    )  # fmt: skip
    connection = BankConnection(
        id=uuid.uuid4(), user_id=OWNER, bank="N26", session_id="s"
    )
    session.add_all([mailbox, connection])
    session.flush()
    email = _email(mailbox.id, f"<owner-{OWNER}@x.example>")
    account = BankAccount(
        id=uuid.uuid4(), connection_id=connection.id, uid="u", identification_hash="h"
    )
    session.add_all([email, account])
    session.flush()
    invoice = Invoice(
        id=uuid.uuid4(), email_id=email.id, position=0, status=InvoiceStatus.OPEN
    )
    tx = Transaction(
        id=uuid.uuid4(), account_id=account.id, booking_date=TODAY, amount=Decimal("-9.99"),
        currency="EUR", remittance="", dedup_key="owner-1", raw={},
    )  # fmt: skip
    thread = ChatThread(id=uuid.uuid4(), user_id=OWNER, agent="finance")
    session.add_all([invoice, tx, thread])
    session.flush()
    return {
        "email": email.id,
        "invoice": invoice.id,
        "transaction": tx.id,
        "thread": thread.id,
    }


def _count(session: Session, model, *where) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where))


def test_reset_rebuilds_only_the_demo_users_finance(session: Session) -> None:
    session.add_all(
        [User(id=OWNER, email="owner@x.example"), User(id=DEMO, email="demo@x.example")]
    )
    session.flush()
    owner = _owner_rows(session)

    reset_demo(session, DEMO, email="demo@x.example", today=TODAY)
    session.commit()

    # Extra demo activity: a new invoice with an approved payment, a booking, a chat.
    accounts = ensure_demo_accounts(session, DEMO)
    extra = _email(accounts.mailbox_id, f"<extra-{DEMO}@x.example>")
    session.add(extra)
    session.flush()
    invoice = Invoice(
        id=uuid.uuid4(), email_id=extra.id, position=0, status=InvoiceStatus.OPEN
    )
    session.add(invoice)
    session.flush()
    extra_invoice_id = invoice.id
    session.add_all([
        PaymentDraft(
            invoice_id=invoice.id, payee="X", iban="DE00", amount=Decimal("5.00"),
            currency="EUR", status=DraftStatus.APPROVED,
        ),
        Transaction(
            account_id=accounts.account_id, booking_date=TODAY, amount=Decimal("-5.00"),
            currency="EUR", remittance="", dedup_key="demo-booking:x", raw={},
        ),
        ChatThread(user_id=DEMO, agent="finance"),
    ])  # fmt: skip
    session.commit()

    counts = reset_demo(session, DEMO, email="demo@x.example", today=TODAY)
    session.commit()

    demo_invoices = (
        select(Invoice.id)
        .join(EmailMessage, EmailMessage.id == Invoice.email_id)
        .where(EmailMessage.mailbox_id == accounts.mailbox_id)
    )
    assert _count(session, Invoice, Invoice.id.in_(demo_invoices)) == 9
    assert (
        _count(session, Transaction, Transaction.account_id == accounts.account_id)
        == (counts["transactions"])
    )
    assert (
        _count(session, PaymentDraft, PaymentDraft.invoice_id.in_(demo_invoices)) == 0
    )
    assert _count(session, ChatThread, ChatThread.user_id == DEMO) == 0
    assert session.get(Invoice, extra_invoice_id) is None
    # The owner's rows are untouched.
    assert session.get(EmailMessage, owner["email"]) is not None
    assert session.get(Invoice, owner["invoice"]) is not None
    assert session.get(Transaction, owner["transaction"]) is not None
    assert session.get(ChatThread, owner["thread"]) is not None

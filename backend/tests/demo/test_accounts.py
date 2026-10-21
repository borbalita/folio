from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.database.models.email.mailbox import Mailbox
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.demo.accounts import ensure_demo_accounts

USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d3")


class _MemorySession:
    """Stores added rows and answers each lookup from the rows of the selected model."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    def scalar(self, statement: object) -> object | None:
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[attr-defined]
        return next((r for r in self.rows if isinstance(r, entity)), None)

    def add(self, row: object) -> None:
        self.rows.append(row)

    def flush(self) -> None:
        for row in self.rows:
            if row.id is None:  # type: ignore[attr-defined]
                row.id = uuid.uuid4()  # type: ignore[attr-defined]


def _of(session: _MemorySession, model: type) -> list:
    return [r for r in session.rows if isinstance(r, model)]


def test_ensure_demo_accounts_is_idempotent() -> None:
    session = _MemorySession()

    first = ensure_demo_accounts(session, USER_ID)  # type: ignore[arg-type]
    second = ensure_demo_accounts(session, USER_ID)  # type: ignore[arg-type]

    assert first == second
    mailbox, connection, account = (
        _of(session, Mailbox)[0],
        _of(session, BankConnection)[0],
        _of(session, BankAccount)[0],
    )
    assert [len(_of(session, m)) for m in (Mailbox, BankConnection, BankAccount)] == [
        1,
        1,
        1,
    ]
    assert (first.mailbox_id, first.account_id) == (mailbox.id, account.id)
    assert (mailbox.provider, mailbox.address, mailbox.display_name) == (
        "demo",
        f"demo+{USER_ID}@folio.example",
        "Demo",
    )
    assert (connection.bank, connection.session_id) == ("Demo Bank", "demo")
    assert connection.valid_until > datetime.now(UTC) + timedelta(days=3000)
    assert account.connection_id == connection.id
    assert (account.uid, account.identification_hash, account.iban) == (
        "demo",
        "demo",
        "DE89370400440532013000",
    )
    assert (account.name, account.currency) == ("Girokonto", "EUR")

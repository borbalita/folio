from __future__ import annotations

import re
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
        params = statement.compile().params  # type: ignore[attr-defined]
        # Each bound parameter is named after its column ("bank_1", "user_id_1", ...).
        wanted = {re.sub(r"_\d+$", "", key): value for key, value in params.items()}
        return next(
            (
                r
                for r in self.rows
                if isinstance(r, entity)
                and all(getattr(r, column) == value for column, value in wanted.items())
            ),
            None,
        )

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
    assert [len(_of(session, m)) for m in (Mailbox, BankConnection, BankAccount)] == [
        1,
        3,
        3,
    ]
    [mailbox] = _of(session, Mailbox)
    assert first.mailbox_id == mailbox.id
    assert (mailbox.provider, mailbox.address, mailbox.display_name) == (
        "demo",
        f"demo+{USER_ID}@folio.example",
        "Demo",
    )


def test_three_demo_banks_with_one_account_each() -> None:
    session = _MemorySession()

    accounts = ensure_demo_accounts(session, USER_ID)  # type: ignore[arg-type]

    connections = {c.id: c for c in _of(session, BankConnection)}
    by_bank = {connections[a.connection_id].bank: a for a in _of(session, BankAccount)}
    assert list(by_bank) == ["Spreeufer Bank", "Kiez Direkt", "TalerPay"]
    assert all(c.session_id == "demo" for c in connections.values())
    assert all(
        c.valid_until > datetime.now(UTC) + timedelta(days=3000)
        for c in connections.values()
    )
    girokonto, alltag, wallet = by_bank.values()
    assert (girokonto.name, girokonto.iban) == ("Girokonto", "DE89370400440532013000")
    assert alltag.name == "Alltagskonto" and alltag.iban is not None
    assert (wallet.name, wallet.iban) == ("TalerPay-Konto", None)
    # Bookings from the presenter page land in the Girokonto.
    assert accounts.account_id == girokonto.id
    assert (accounts.card_account_id, accounts.wallet_account_id) == (
        alltag.id,
        wallet.id,
    )
    assert accounts.account_ids == (girokonto.id, alltag.id, wallet.id)

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.database import bank_connections
from app.database.models.finance.bank_connection import BankConnection
from app.finance.enable_banking import EbAccount, EbSession

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _account(uid: str, iban: str | None) -> EbAccount:
    return EbAccount(
        uid=uid, identification_hash=f"h-{uid}", iban=iban, name=uid, currency="EUR"
    )


def _patch_session(monkeypatch: pytest.MonkeyPatch, session: MagicMock) -> None:
    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(bank_connections, "get_session", fake_get_session)


def test_n26_keeps_only_the_main_account() -> None:
    main = _account("main", "DE89370400440532013000")
    spaces = [_account(f"space{i}", None) for i in range(3)]

    assert bank_connections.keep_accounts("N26", [main, *spaces]) == [main]


def test_other_banks_keep_accounts_without_iban() -> None:
    paypal = _account("pp", None)

    assert bank_connections.keep_accounts("PayPal", [paypal]) == [paypal]


def test_complete_connection_with_unknown_state_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.scalar.return_value = None
    _patch_session(monkeypatch, session)
    eb_session = EbSession("s", datetime(2027, 1, 1, tzinfo=UTC), [])

    with pytest.raises(bank_connections.UnknownState):
        bank_connections.complete_connection(USER_ID, "nope", eb_session)


def test_complete_connection_stores_session_clears_state_and_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = BankConnection(
        id=uuid.uuid4(), user_id=USER_ID, bank="ING", pending_state="state-1"
    )
    session = MagicMock()
    session.scalar.return_value = connection
    _patch_session(monkeypatch, session)
    valid_until = datetime(2027, 1, 1, tzinfo=UTC)
    eb_session = EbSession("s1", valid_until, [_account("a", "DE89370400440532013000")])

    bank_connections.complete_connection(USER_ID, "state-1", eb_session)

    assert connection.session_id == "s1"
    assert connection.valid_until == valid_until
    assert connection.pending_state is None
    session.execute.assert_called_once()
    upsert_sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in upsert_sql
    session.commit.assert_called_once()


def test_account_upsert_conflicts_on_identification_hash() -> None:
    stmt = bank_connections.account_upsert(
        uuid.uuid4(), [_account("a", "DE89370400440532013000")]
    )

    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT (connection_id, identification_hash) DO UPDATE" in sql
    for column in ("uid", "iban", "name", "currency"):
        assert f"{column} = excluded.{column}" in sql


def test_mask_iban() -> None:
    assert bank_connections.mask_iban("DE89370400440532013000") == "DE89 •••• 3000"
    assert bank_connections.mask_iban(None) is None


def test_list_connections_lists_all_banks_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.scalars.return_value = []
    _patch_session(monkeypatch, session)

    result = bank_connections.list_connections(USER_ID)

    assert result == [
        {"bank": bank, "connected": False, "validUntil": None, "accounts": []}
        for bank in ("N26", "ING", "PayPal")
    ]

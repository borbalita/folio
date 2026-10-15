from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.database import bank_connections
from app.database.models.finance.bank_account import BankAccount
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
        {"bank": bank, "connected": False, "validUntil": None, "status": None, "accounts": []}
        for bank in ("N26", "ING", "PayPal")
    ]


def _row(hash_: str, iban: str | None) -> BankAccount:
    return BankAccount(
        id=uuid.uuid4(), connection_id=uuid.uuid4(), uid="old", identification_hash=hash_, iban=iban
    )


def test_reconnect_keeps_existing_account_rows() -> None:
    same_hash = _row("h-a", "DE89370400440532013000")
    new_hash_same_iban = _row("h-old", "DE02120300000000202051")
    unrelated = _row("h-x", None)
    incoming = [
        _account("a", "DE89370400440532013000"),
        EbAccount(
            uid="b", identification_hash="h-new", iban="DE02120300000000202051",
            name="b", currency="EUR",
        ),
    ]

    bank_connections.rehash_by_iban([same_hash, new_hash_same_iban, unrelated], incoming)

    # The upsert then matches both rows by hash, so their ids, and the
    # transactions pointing at them, stay.
    assert same_hash.identification_hash == "h-a"
    assert new_hash_same_iban.identification_hash == "h-new"
    assert unrelated.identification_hash == "h-x"


def test_reconnect_clears_invalid_and_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = BankConnection(
        id=uuid.uuid4(), user_id=USER_ID, bank="ING", pending_state="state-1",
        invalidated_at=datetime(2026, 10, 1, tzinfo=UTC), expiry_notice="expired",
    )
    session = MagicMock()
    session.scalar.return_value = connection
    session.scalars.return_value = []
    _patch_session(monkeypatch, session)

    bank_connections.complete_connection(
        USER_ID, "state-1", EbSession("s2", datetime(2027, 4, 1, tzinfo=UTC), [])
    )

    assert connection.invalidated_at is None
    assert connection.expiry_notice is None


def test_list_connections_reports_status(monkeypatch: pytest.MonkeyPatch) -> None:
    soon = datetime.now(UTC) + timedelta(days=5)
    connection = BankConnection(
        id=uuid.uuid4(), user_id=USER_ID, bank="ING", session_id="s", valid_until=soon,
        invalidated_at=None,
    )
    session = MagicMock()
    session.scalars.side_effect = [[connection], []]
    _patch_session(monkeypatch, session)

    ing = next(c for c in bank_connections.list_connections(USER_ID) if c["bank"] == "ING")

    assert ing["status"] == "expiring"


def test_complete_connection_rehashes_before_the_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = BankConnection(
        id=uuid.uuid4(), user_id=USER_ID, bank="ING", pending_state="state-1"
    )
    existing = _row("h-old", "DE02120300000000202051")
    session = MagicMock()
    session.scalar.return_value = connection
    session.scalars.return_value = [existing]
    calls: list[str] = []
    session.flush.side_effect = lambda: calls.append("flush")
    session.execute.side_effect = lambda stmt: calls.append("upsert")
    _patch_session(monkeypatch, session)
    incoming = EbAccount(
        uid="new-uid", identification_hash="h-new", iban="DE02120300000000202051",
        name="ING", currency="EUR",
    )

    bank_connections.complete_connection(
        USER_ID, "state-1", EbSession("s2", datetime(2027, 4, 1, tzinfo=UTC), [incoming])
    )

    # The existing row now carries the new hash, so the upsert updates it in place.
    assert existing.identification_hash == "h-new"
    assert calls == ["flush", "upsert"]

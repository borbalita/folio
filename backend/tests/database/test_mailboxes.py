from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.database import mailboxes

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _sql_of(monkeypatch: pytest.MonkeyPatch, lookup) -> tuple[str, dict]:
    session = MagicMock()
    session.scalars.return_value = []

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(mailboxes, "get_session", fake_get_session)
    lookup(USER_ID)
    compiled = session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def test_active_mailbox_ids_excludes_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    sql, params = _sql_of(monkeypatch, mailboxes.active_mailbox_ids)

    assert "mailboxes.provider != " in sql
    assert "demo" in params.values()


def test_invoice_mailbox_ids_includes_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    sql, params = _sql_of(monkeypatch, mailboxes.invoice_mailbox_ids)

    assert "mailboxes.provider" not in sql.split("WHERE")[1]
    assert "demo" not in params.values()
    assert "mailboxes.is_active" in sql


def test_news_mailbox_ids_includes_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    sql, params = _sql_of(monkeypatch, mailboxes.news_mailbox_ids)

    assert "mailboxes.provider" not in sql.split("WHERE")[1]
    assert "demo" not in params.values()

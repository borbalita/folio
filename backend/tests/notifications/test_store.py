from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.notifications import store
from app.notifications.detect import NewNotification


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_insert_rows_ignores_keys_already_recorded() -> None:
    session = MagicMock()

    store.insert_rows(session, [NewNotification("invoice_new:x", "invoice_new", "pending", "t")])

    sql = _sql(session.execute.call_args.args[0])
    assert sql.startswith("INSERT INTO notifications")
    assert "ON CONFLICT (key) DO NOTHING" in sql


def test_insert_rows_with_nothing_does_not_touch_the_database() -> None:
    session = MagicMock()

    store.insert_rows(session, [])

    session.execute.assert_not_called()


def test_enabled_needs_all_three_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "1")
    monkeypatch.setattr(settings, "app_url", "https://folio.test")
    assert store.telegram_enabled()

    monkeypatch.setattr(settings, "telegram_chat_id", None)
    assert not store.telegram_enabled()


def test_record_uses_berlin_date_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    inv = SimpleNamespace(
        id=uuid.uuid4(), email_id=uuid.uuid4(), status="open", payee="P",
        amount=Decimal("1.00"), currency="EUR", due_date=date(2026, 10, 20),
    )
    monkeypatch.setattr(store, "load_invoices", lambda session: [store.invoice_facts(inv, "s@x")])
    monkeypatch.setattr(store, "load_big_stories", lambda session, since: seen.setdefault("since", since) and [])
    monkeypatch.setattr(store, "known_keys", lambda session: set())

    def plan(invoices, stories, known, *, today, app_url, enabled):
        seen["today"] = today
        return [NewNotification("invoice_new:1", "invoice_new", "pending", "t")]

    monkeypatch.setattr(store, "plan_notifications", plan)
    session = MagicMock()

    # 23:30 UTC on the 19th is already the 20th in Berlin.
    added = store.record_notifications(session, datetime(2026, 10, 19, 23, 30, tzinfo=UTC))

    assert seen["today"] == date(2026, 10, 20)
    assert seen["since"] == date(2026, 10, 18)
    assert added == 1
    session.commit.assert_called_once()



def test_only_recent_big_stories_are_read() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value = []

    store.load_big_stories(session, since=date(2026, 10, 17))

    sql = _sql(session.execute.call_args.args[0])
    assert "news_stories.is_big IS true" in sql
    assert "news_stories.last_seen >= " in sql


def test_load_invoices_skips_demo_mailboxes() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_invoices(session)

    statement = session.execute.call_args.args[0]
    sql = _sql(statement)
    assert "mailboxes.provider !=" in sql
    params = statement.compile(dialect=postgresql.dialect()).params
    assert "demo" in params.values()


def test_big_stories_exclude_demo_mailboxes() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value = []

    store.load_big_stories(session, date(2026, 10, 1))

    statement = session.execute.call_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "JOIN emails ON emails.id = news_items.email_id" in sql
    assert "JOIN mailboxes ON mailboxes.id = emails.mailbox_id" in sql
    assert "mailboxes.provider != 'demo'" in sql

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app.database import news_story
from tests.news_fakes import FakeNewsDb, news_row

MINE = uuid.UUID(int=10)
OTHERS = uuid.UUID(int=11)


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_reading_an_item_filters_on_the_mailboxes_in_the_query() -> None:
    sql = _sql(news_story.item_statement([MINE], uuid.uuid4()))

    assert "emails.mailbox_id IN" in sql.split("\nWHERE ", 1)[1]
    assert "news_items.id = " in sql


def test_resolving_refs_keys_on_email_and_position_not_item_ids() -> None:
    sql = _sql(news_story.refs_statement([MINE], [(uuid.uuid4(), 3)]))
    where = sql.split("\nWHERE ", 1)[1]

    assert "emails.mailbox_id IN" in where
    assert "(news_items.email_id, news_items.position) IN" in where
    assert "news_items.id" not in where


def test_another_users_item_reads_as_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    theirs = news_row(mailbox_id=OTHERS, body="secret")
    db = FakeNewsDb([theirs])
    monkeypatch.setattr(news_story, "get_session", db.session)

    assert news_story.read_story([MINE], theirs.id) is None


def test_own_item_reads_with_the_whole_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    mine = news_row(mailbox_id=MINE, body="Whole edition.")
    monkeypatch.setattr(news_story, "get_session", FakeNewsDb([mine]).session)

    found = news_story.read_story([MINE], mine.id)

    assert found is not None
    assert found.body == "Whole edition."
    assert found.item.item_id == mine.id and found.item.title == mine.title


def test_refs_are_owned_only_when_every_one_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    mine = news_row(mailbox_id=MINE, position=1)
    theirs = news_row(mailbox_id=OTHERS, position=2)
    monkeypatch.setattr(news_story, "get_session", FakeNewsDb([mine, theirs]).session)

    assert news_story.owns_all([MINE], [(mine.email_id, 1)])
    assert not news_story.owns_all([MINE], [(mine.email_id, 1), (theirs.email_id, 2)])
    assert not news_story.owns_all([MINE], [(uuid.uuid4(), 0)])


def test_no_mailboxes_means_no_query(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeNewsDb([news_row(mailbox_id=MINE)])
    monkeypatch.setattr(news_story, "get_session", db.session)

    assert news_story.read_story([], db.rows[0].id) is None
    assert not news_story.owns_all([], [(db.rows[0].email_id, 0)])
    assert db.statements == []

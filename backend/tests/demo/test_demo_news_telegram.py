from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.demo import news_telegram
from app.notifications import summary, telegram

USER = uuid.uuid4()


def _item(title: str, story: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email_id=uuid.uuid4(),
        position=1,
        source="demo_tensor",
        title=title,
        blurb="b",
        url="https://x.test/" + title,
        story_id=story,
    )


def _session(rows: list[tuple[SimpleNamespace, date]]) -> MagicMock:
    session = MagicMock()
    session.execute.return_value.all.return_value = rows
    return session


@pytest.fixture
def telegram_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "tok")
    monkeypatch.setattr(settings, "telegram_chat_id", "42")


def _use(monkeypatch: pytest.MonkeyPatch, session: MagicMock) -> None:
    @contextmanager
    def fake():
        yield session

    monkeypatch.setattr(news_telegram, "get_session", fake)


def test_only_the_users_demo_mailbox_big_stories_are_loaded() -> None:
    session = _session([])

    news_telegram.load_demo_stories(session, USER)

    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "mailboxes.provider = " in sql
    assert "mailboxes.user_id = " in sql
    assert "news_stories.is_big IS true" in sql
    assert "news_stories.last_seen >= " in sql


def test_most_covered_story_ranks_first_then_latest() -> None:
    session = _session(
        [
            (_item("a1", "A"), date(2026, 1, 5)),
            (_item("b1", "B"), date(2026, 1, 3)),
            (_item("b2", "B"), date(2026, 1, 3)),
            (_item("c1", "C"), date(2026, 1, 9)),
        ]
    )

    stories = news_telegram.load_demo_stories(session, USER)

    assert [[i.title for i in s] for s in stories] == [["b1", "b2"], ["c1"], ["a1"]]


def test_the_summary_goes_to_the_chat_and_adds_no_row(
    monkeypatch: pytest.MonkeyPatch, telegram_on: None
) -> None:
    session = _session(
        [(_item("a1", "A"), date(2026, 1, 5)), (_item("a2", "A"), date(2026, 1, 5))]
    )
    _use(monkeypatch, session)
    seen: list[list[str]] = []
    monkeypatch.setattr(
        summary,
        "news_text",
        lambda items: seen.append([i.title for i in items]) or "📰 Head\nbody",
    )
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(200, json={"ok": True})

    result = news_telegram.send_demo_summary(
        USER, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert result == {"sent": True, "headline": "Head"}
    assert seen == [["a1", "a2"]]
    [request] = posts
    assert json.loads(request.content) == {"chat_id": "42", "text": "📰 Head\nbody"}
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_without_telegram_settings_nothing_is_read_or_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    monkeypatch.setattr(news_telegram, "get_session", lambda: pytest.fail("no db"))

    with pytest.raises(news_telegram.TelegramNotConfigured):
        news_telegram.send_demo_summary(USER)


def test_no_big_stories(monkeypatch: pytest.MonkeyPatch, telegram_on: None) -> None:
    _use(monkeypatch, _session([]))

    with pytest.raises(news_telegram.NoBigStories):
        news_telegram.send_demo_summary(USER)


def test_send_text_raises_without_leaking_the_token(telegram_on: None) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400)))

    with pytest.raises(telegram.SendError) as caught:
        telegram.send_text("hi", client=client)

    assert "tok" not in str(caught.value)
    assert "400" in str(caught.value)


def test_send_text_hides_the_url_of_a_network_error(telegram_on: None) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed for " + str(request.url))

    client = httpx.Client(transport=httpx.MockTransport(boom))

    with pytest.raises(telegram.SendError) as caught:
        telegram.send_text("hi", client=client)

    assert "tok" not in str(caught.value)
    assert caught.value.__cause__ is None

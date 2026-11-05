from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import mailboxes, news_feed

MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000010")


def test_a_user_without_an_active_mailbox_gets_403(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [])

    assert authed_client.get("/news/stories").status_code == 403


def test_the_list_is_built_from_the_users_news_mailboxes_only(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple] = []
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [MAILBOX])

    def list_stories(mailbox_ids, *, before, days, only_big):
        seen.append((mailbox_ids, before, days, only_big))
        return {"days": [], "nextBefore": None}

    monkeypatch.setattr(news_feed, "list_stories", list_stories)

    response = authed_client.get("/news/stories?before=2026-11-01&days=7&only=big")

    assert response.status_code == 200
    assert response.json() == {"days": [], "nextBefore": None}
    assert seen == [([MAILBOX], date(2026, 11, 1), 7, True)]


def test_without_parameters_the_window_ends_after_today(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple] = []
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [MAILBOX])
    monkeypatch.setattr(
        news_feed,
        "list_stories",
        lambda ids, *, before, days, only_big: seen.append((before, days, only_big))
        or {"days": [], "nextBefore": None},
    )

    authed_client.get("/news/stories")

    (before, days, only_big) = seen[0]
    assert days == 14 and only_big is False
    assert before > date(2026, 11, 5)


def test_an_unknown_filter_is_rejected(authed_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [MAILBOX])

    assert authed_client.get("/news/stories?only=security").status_code == 422

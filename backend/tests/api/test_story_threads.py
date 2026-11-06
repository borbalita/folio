from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import chats, mailboxes, news_story
from tests.conftest import TEST_THREAD_ID
from tests.news_fakes import FakeNewsDb, news_row

MINE = uuid.UUID(int=10)
OTHERS = uuid.UUID(int=11)


@pytest.fixture
def create_thread(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value={"id": str(TEST_THREAD_ID), "title": "Story"})
    monkeypatch.setattr(chats, "create_thread_for_user", mock)
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [MINE])
    return mock


def _post(client: TestClient, agent: str, refs: list[tuple[uuid.UUID, int]]):
    return client.post(
        "/threads",
        json={
            "title": "Story",
            "agent": agent,
            "story_items": [{"email_id": str(e), "position": p} for e, p in refs],
        },
    )


def test_story_items_in_the_users_mailboxes_are_stored(
    authed_client: TestClient, create_thread: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = news_row(mailbox_id=MINE, position=2)
    monkeypatch.setattr(news_story, "get_session", FakeNewsDb([mine]).session)

    response = _post(authed_client, "news", [(mine.email_id, 2)])

    assert response.status_code == 200
    stored = create_thread.call_args.args[-1]
    assert stored == [{"email_id": str(mine.email_id), "position": 2}]


def test_story_items_pointing_at_another_users_mail_are_rejected(
    authed_client: TestClient, create_thread: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    theirs = news_row(mailbox_id=OTHERS, position=2)
    monkeypatch.setattr(news_story, "get_session", FakeNewsDb([theirs]).session)

    response = _post(authed_client, "news", [(theirs.email_id, 2)])

    assert response.status_code == 400
    create_thread.assert_not_called()


def test_story_items_are_only_for_news_threads(
    authed_client: TestClient, create_thread: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = news_row(mailbox_id=MINE)
    monkeypatch.setattr(news_story, "get_session", FakeNewsDb([mine]).session)

    response = _post(authed_client, "documents", [(mine.email_id, 0)])

    assert response.status_code == 422
    create_thread.assert_not_called()


def test_an_empty_story_items_list_is_refused(
    authed_client: TestClient, create_thread: MagicMock
) -> None:
    assert _post(authed_client, "news", []).status_code == 422

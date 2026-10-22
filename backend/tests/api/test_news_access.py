from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser
from app.auth.email_access import require_agent_access
from app.config import settings
from app.database import mailboxes
from tests.conftest import TEST_USER_ID

MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000010")


def _scopes(
    monkeypatch: pytest.MonkeyPatch, *, email: list[uuid.UUID], news: list[uuid.UUID]
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: email)
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: news)


def test_demo_user_gets_news_and_finance_but_not_email(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scopes(monkeypatch, email=[], news=[MAILBOX])
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)

    response = authed_client.get("/me")

    assert response.json()["agents"] == ["documents", "news", "finance"]


def test_owner_with_a_real_mailbox_gets_email_news_and_finance(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scopes(monkeypatch, email=[MAILBOX], news=[MAILBOX])
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)

    response = authed_client.get("/me")

    assert response.json()["agents"] == ["documents", "email", "news", "finance"]


def test_news_access_follows_the_news_scope_not_the_email_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = CurrentUser(id=TEST_USER_ID, email="a@example.com")
    _scopes(monkeypatch, email=[], news=[MAILBOX])

    asyncio.run(require_agent_access(user, "news"))
    with pytest.raises(HTTPException) as denied:
        asyncio.run(require_agent_access(user, "email"))

    assert denied.value.status_code == 403


def test_news_is_forbidden_without_any_mailbox(monkeypatch: pytest.MonkeyPatch) -> None:
    user = CurrentUser(id=TEST_USER_ID, email="a@example.com")
    _scopes(monkeypatch, email=[MAILBOX], news=[])

    with pytest.raises(HTTPException) as denied:
        asyncio.run(require_agent_access(user, "news"))

    assert denied.value.status_code == 403

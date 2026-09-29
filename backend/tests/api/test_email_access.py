from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import chats, mailboxes
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID


def _no_mailbox(user_id: uuid.UUID) -> list[uuid.UUID]:
    return []


def _owns_mailbox(user_id: uuid.UUID) -> list[uuid.UUID]:
    return [uuid.UUID("00000000-0000-0000-0000-000000000010")]


def _email_thread(thread_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, str]:
    return {"id": str(thread_id), "title": "Mail", "agent": "email"}


def test_me_lists_documents_only_without_a_mailbox(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _no_mailbox)

    response = authed_client.get("/me")

    assert response.status_code == 200
    assert response.json()["agents"] == ["documents"]


def test_me_includes_email_for_an_active_mailbox(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)

    response = authed_client.get("/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(TEST_USER_ID)
    assert body["agents"] == ["documents", "email"]


def test_email_routes_are_forbidden_without_a_mailbox(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _no_mailbox)
    monkeypatch.setattr(chats, "get_thread_for_user", _email_thread)

    listed = authed_client.get("/threads", params={"agent": "email"})
    created = authed_client.post("/threads", json={"agent": "email"})
    posted = authed_client.post(
        "/chat/stream",
        json={"threadId": str(TEST_THREAD_ID), "messages": []},
    )

    assert listed.status_code == 403
    assert created.status_code == 403
    assert posted.status_code == 403


def test_owner_can_list_create_and_post_to_email(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    monkeypatch.setattr(chats, "list_threads", lambda user_id, agent: [])
    monkeypatch.setattr(
        chats,
        "create_thread_for_user",
        lambda user_id, email, title=None, agent="documents": {
            "id": str(TEST_THREAD_ID),
            "title": title or "New chat",
            "agent": agent,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(chats, "get_thread_for_user", _email_thread)
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    listed = authed_client.get("/threads", params={"agent": "email"})
    created = authed_client.post("/threads", json={"agent": "email"})
    posted = authed_client.post(
        "/chat/stream",
        json={"threadId": str(TEST_THREAD_ID), "messages": []},
    )

    assert listed.status_code == 200
    assert created.status_code == 200
    assert created.json()["agent"] == "email"
    assert posted.status_code == 200


def test_document_routes_stay_open_without_a_mailbox(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _no_mailbox)
    monkeypatch.setattr(chats, "list_threads", lambda user_id, agent: [])
    monkeypatch.setattr(
        chats,
        "create_thread_for_user",
        lambda user_id, email, title=None, agent="documents": {
            "id": str(TEST_THREAD_ID),
            "title": "New chat",
            "agent": agent,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        chats,
        "get_thread_for_user",
        lambda thread_id, user_id: {
            "id": str(thread_id),
            "title": "Docs",
            "agent": "documents",
        },
    )
    monkeypatch.setattr(chats, "list_messages", lambda thread_id: [])

    assert authed_client.get("/threads").status_code == 200
    assert authed_client.post("/threads", json={}).status_code == 200
    messages = authed_client.get(f"/threads/{TEST_THREAD_ID}/messages")
    assert messages.status_code == 200

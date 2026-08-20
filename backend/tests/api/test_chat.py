from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import chats
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID


def test_list_threads_requires_auth(client: TestClient) -> None:
    response = client.get("/threads")
    assert response.status_code == 401


def test_get_messages_returns_not_found(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_not_found(thread_id: uuid.UUID, user_id: uuid.UUID) -> None:
        raise HTTPException(status_code=404, detail="Thread not found")

    monkeypatch.setattr(chats, "get_thread_for_user", raise_not_found)

    response = authed_client.get(f"/threads/{TEST_THREAD_ID}/messages")

    assert response.status_code == 404


def test_get_messages_returns_forbidden(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_forbidden(thread_id: uuid.UUID, user_id: uuid.UUID) -> None:
        raise HTTPException(status_code=403, detail="Forbidden")

    monkeypatch.setattr(chats, "get_thread_for_user", raise_forbidden)

    response = authed_client.get(f"/threads/{TEST_THREAD_ID}/messages")

    assert response.status_code == 403


def test_get_messages_returns_rows(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chats,
        "get_thread_for_user",
        lambda thread_id, user_id: {"id": str(thread_id), "title": "Test"},
    )
    monkeypatch.setattr(
        chats,
        "list_messages",
        lambda thread_id: [
            {
                "id": "msg-1",
                "role": "user",
                "message": {"role": "user", "content": "hi"},
                "sequenceNumber": 1,
                "createdAt": "2026-01-01T00:00:00Z",
            },
        ],
    )

    response = authed_client.get(f"/threads/{TEST_THREAD_ID}/messages")

    assert response.status_code == 200
    assert response.json()[0]["role"] == "user"


def test_chat_stream_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/chat/stream",
        json={"threadId": str(TEST_THREAD_ID), "messages": []},
    )
    assert response.status_code == 401


def test_chat_stream_returns_forbidden_before_stream(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_forbidden(thread_id: uuid.UUID, user_id: uuid.UUID) -> None:
        raise HTTPException(status_code=403, detail="Forbidden")

    monkeypatch.setattr(chats, "get_thread_for_user", raise_forbidden)

    response = authed_client.post(
        "/chat/stream",
        json={"threadId": str(TEST_THREAD_ID), "messages": []},
    )

    assert response.status_code == 403


def test_create_thread_calls_persistence(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_thread = MagicMock(
        return_value={
            "id": str(TEST_THREAD_ID),
            "title": "New chat",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(chats, "create_thread_for_user", create_thread)

    response = authed_client.post("/threads", json={"title": "My thread"})

    assert response.status_code == 200
    create_thread.assert_called_once_with(
        TEST_USER_ID,
        "test@example.com",
        "My thread",
    )

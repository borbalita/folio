from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.database import chats

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
THREAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _mock_admin_client(*, rows: list[dict]) -> MagicMock:
    client = MagicMock()
    (
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    ).return_value = MagicMock(data=rows)
    return client


def test_get_thread_for_user_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chats,
        "get_admin_client",
        lambda: _mock_admin_client(rows=[]),
    )

    with pytest.raises(HTTPException) as exc_info:
        chats.get_thread_for_user(THREAD_ID, USER_ID)

    assert exc_info.value.status_code == 404


def test_get_thread_for_user_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chats,
        "get_admin_client",
        lambda: _mock_admin_client(
            rows=[
                {
                    "id": str(THREAD_ID),
                    "user_id": str(OTHER_USER_ID),
                    "title": "Secret",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            ],
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        chats.get_thread_for_user(THREAD_ID, USER_ID)

    assert exc_info.value.status_code == 403


def test_get_thread_for_user_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chats,
        "get_admin_client",
        lambda: _mock_admin_client(
            rows=[
                {
                    "id": str(THREAD_ID),
                    "user_id": str(USER_ID),
                    "title": "Mine",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            ],
        ),
    )

    row = chats.get_thread_for_user(THREAD_ID, USER_ID)

    assert row["id"] == str(THREAD_ID)
    assert row["title"] == "Mine"

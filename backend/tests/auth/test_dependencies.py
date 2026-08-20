from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

from app.auth import dependencies as auth_dependencies


def test_me_requires_authorization(client: TestClient) -> None:
    response = client.get("/me")
    assert response.status_code == 401


def test_me_rejects_invalid_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    get_user = AsyncMock(side_effect=AuthApiError("invalid", 401, None))
    monkeypatch.setattr(
        auth_dependencies,
        "_auth_client",
        lambda: _mock_auth_client(get_user=get_user),
    )

    response = client.get("/me", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_me_returns_current_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    get_user = AsyncMock(
        return_value=SimpleNamespace(
            user=SimpleNamespace(id=str(user_id), email="test@example.com"),
        ),
    )
    monkeypatch.setattr(
        auth_dependencies,
        "_auth_client",
        lambda: _mock_auth_client(get_user=get_user),
    )

    response = client.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user_id),
        "email": "test@example.com",
    }


def _mock_auth_client(*, get_user: AsyncMock) -> MagicMock:
    client = MagicMock()
    client.auth.get_user = get_user
    return client

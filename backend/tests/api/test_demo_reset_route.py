from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import chats
from app.demo import reset
from tests.conftest import TEST_USER_ID


def test_reset_route_does_not_exist_without_a_demo_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", None)

    assert authed_client.post("/finance/demo/reset").status_code == 404


def test_the_owner_cannot_reset_the_demo(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(reset, "run_reset", lambda *a, **k: pytest.fail("not called"))

    assert authed_client.post("/finance/demo/reset").status_code == 403


def test_the_demo_user_resets_their_finance(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    users: list[tuple[uuid.UUID, str]] = []
    resets: list[uuid.UUID] = []
    monkeypatch.setattr(
        chats, "ensure_user", lambda user_id, email: users.append((user_id, email))
    )
    monkeypatch.setattr(
        reset,
        "run_reset",
        lambda user_id, email: (
            resets.append(user_id) or {"invoices": 9, "transactions": 36}
        ),
    )

    response = authed_client.post("/finance/demo/reset")

    assert response.status_code == 200
    assert response.json() == {"invoices": 9, "transactions": 36}
    assert [user_id for user_id, _ in users] == [TEST_USER_ID]
    assert resets == [TEST_USER_ID]

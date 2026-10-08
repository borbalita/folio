from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import mailboxes
from tests.conftest import TEST_USER_ID


@pytest.fixture(autouse=True)
def no_mailbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [])


def test_me_lists_finance_for_the_owner(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)

    response = authed_client.get("/me")

    assert response.status_code == 200
    assert response.json()["agents"] == ["documents", "finance"]


def test_me_omits_finance_for_another_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    assert authed_client.get("/me").json()["agents"] == ["documents"]


def test_finance_is_off_for_everyone_when_unset(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", None)

    assert authed_client.get("/me").json()["agents"] == ["documents"]
    assert authed_client.get("/finance/access").status_code == 403


def test_owner_can_reach_finance_routes(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)

    assert authed_client.get("/finance/access").status_code == 200


def test_finance_routes_are_forbidden_for_another_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    assert authed_client.get("/finance/access").status_code == 403
    assert authed_client.get("/threads", params={"agent": "finance"}).status_code == 403
    assert authed_client.post("/threads", json={"agent": "finance"}).status_code == 403

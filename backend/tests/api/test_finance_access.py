from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import chats, mailboxes
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
    # A mailbox is present, so only the owner check can produce the 403.
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])
    assert authed_client.get("/finance/invoices").status_code == 403


def test_finance_routes_are_forbidden_for_another_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    # A mailbox is present, so only the owner check can produce the 403.
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])
    assert authed_client.get("/finance/invoices").status_code == 403
    assert authed_client.get("/threads", params={"agent": "finance"}).status_code == 403
    assert authed_client.post("/threads", json={"agent": "finance"}).status_code == 403


def test_former_owner_cannot_use_an_existing_finance_thread(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread_id = uuid.uuid4()
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    # A mailbox is present, so only the owner check can produce the 403.
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])
    monkeypatch.setattr(
        chats,
        "get_thread_for_user",
        lambda thread_id, user_id: {"id": str(thread_id), "agent": "finance"},
    )

    assert authed_client.get(f"/threads/{thread_id}/messages").status_code == 403
    assert authed_client.delete(f"/threads/{thread_id}").status_code == 403
    stream = authed_client.post(
        "/chat/stream", json={"thread_id": str(thread_id), "messages": []}
    )
    assert stream.status_code == 403

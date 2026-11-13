from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.phone import get_call_limiter
from app.config import settings
from app.database import mailboxes
from app.main import app
from app.phone import session
from app.phone.personas import persona_by_id
from app.phone.session import CallLimiter, session_config
from tests.conftest import TEST_USER_ID


class FakeClientSecrets:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(value="ek_test", expires_at=1_900_000_000)


@pytest.fixture
def secrets(monkeypatch: pytest.MonkeyPatch) -> FakeClientSecrets:
    fake = FakeClientSecrets()
    client = SimpleNamespace(realtime=SimpleNamespace(client_secrets=fake))
    monkeypatch.setattr(session, "realtime_client", lambda: client)
    return fake


@pytest.fixture(autouse=True)
def no_mailboxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [])
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [])


@pytest.fixture
def demo_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)


def _limit(per_hour: int) -> None:
    limiter = CallLimiter(per_hour=per_hour)
    app.dependency_overrides[get_call_limiter] = lambda: limiter


def test_other_users_get_no_phone_and_403(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    secrets: FakeClientSecrets,
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())

    assert "phone" not in authed_client.get("/me").json()["agents"]
    assert authed_client.get("/phone/personas").status_code == 403
    assert (
        authed_client.post("/phone/session", json={"persona": "friend"}).status_code
        == 403
    )
    assert secrets.calls == []


def test_owner_gets_phone(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)

    assert "phone" in authed_client.get("/me").json()["agents"]


def test_demo_user_gets_a_friend_secret(
    authed_client: TestClient, demo_user: None, secrets: FakeClientSecrets
) -> None:
    _limit(10)

    response = authed_client.post("/phone/session", json={"persona": "friend"})

    assert response.status_code == 200
    assert response.json() == {
        "secret": "ek_test",
        "expiresAt": 1_900_000_000,
        "maxSeconds": settings.phone_call_max_seconds,
    }
    friend = persona_by_id("friend")
    assert friend is not None
    assert secrets.calls[0]["session"] == session_config(friend)


def test_personas_list_marks_who_can_be_called(
    authed_client: TestClient, demo_user: None
) -> None:
    personas = authed_client.get("/phone/personas").json()

    assert [(p["id"], p["available"]) for p in personas] == [
        ("friend", True),
        ("doctor", False),
        ("interviewer", False),
    ]
    assert all(p["name"] and p["description"] for p in personas)


@pytest.mark.parametrize("persona", ["doctor", "pirate"])
def test_unavailable_or_unknown_persona_is_404(
    authed_client: TestClient, demo_user: None, secrets: FakeClientSecrets, persona: str
) -> None:
    _limit(10)

    response = authed_client.post("/phone/session", json={"persona": persona})

    assert response.status_code == 404
    assert secrets.calls == []


def test_calls_over_the_hourly_limit_are_429(
    authed_client: TestClient, demo_user: None, secrets: FakeClientSecrets
) -> None:
    _limit(1)

    first = authed_client.post("/phone/session", json={"persona": "friend"})
    second = authed_client.post("/phone/session", json={"persona": "friend"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert len(secrets.calls) == 1

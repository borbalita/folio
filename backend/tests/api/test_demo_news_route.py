from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.demo import news_telegram
from app.notifications.telegram import SendError
from tests.conftest import TEST_USER_ID


def test_route_does_not_exist_without_a_demo_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", None)

    assert authed_client.post("/finance/demo/news-summary").status_code == 404


def test_the_owner_cannot_send(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(
        news_telegram, "send_demo_summary", lambda *a, **k: pytest.fail("no")
    )

    assert authed_client.post("/finance/demo/news-summary").status_code == 403


def test_the_demo_user_sends_a_summary(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    monkeypatch.setattr(
        news_telegram,
        "send_demo_summary",
        lambda user_id: {"sent": True, "headline": "H"},
    )

    response = authed_client.post("/finance/demo/news-summary")

    assert response.status_code == 200
    assert response.json() == {"sent": True, "headline": "H"}


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (news_telegram.TelegramNotConfigured(), 409, "Telegram is not configured"),
        (news_telegram.NoBigStories(), 404, "No big demo stories"),
        (SendError("Telegram answered 400"), 502, "Telegram answered 400"),
    ],
)
def test_failures_map_to_statuses(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
    detail: str,
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)

    def fail(user_id: uuid.UUID) -> None:
        raise error

    monkeypatch.setattr(news_telegram, "send_demo_summary", fail)

    response = authed_client.post("/finance/demo/news-summary")

    assert response.status_code == status
    assert response.json()["detail"] == detail

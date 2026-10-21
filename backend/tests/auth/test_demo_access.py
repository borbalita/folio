from __future__ import annotations

import uuid
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.demo_access import is_demo_user, require_demo_user
from app.auth.dependencies import CurrentUser, get_current_user
from app.config import settings
from tests.conftest import TEST_USER_ID


@pytest.fixture
def demo_client(current_user: CurrentUser) -> TestClient:
    app = FastAPI()

    @app.get("/demo-only")
    def demo_only(
        user: Annotated[CurrentUser, Depends(require_demo_user)],
    ) -> dict[str, str]:
        return {"id": str(user.id)}

    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def test_demo_route_is_404_without_demo_user(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", None)

    assert demo_client.get("/demo-only").status_code == 404


def test_demo_route_is_403_for_the_owner(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())

    assert demo_client.get("/demo-only").status_code == 403


def test_demo_route_answers_for_the_demo_user(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)

    response = demo_client.get("/demo-only")

    assert response.status_code == 200
    assert response.json() == {"id": str(TEST_USER_ID)}


def test_is_demo_user_is_false_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_user_id", None)

    assert not is_demo_user(TEST_USER_ID)

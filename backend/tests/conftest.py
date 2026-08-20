from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, get_current_user
from app.main import app

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_THREAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def current_user() -> CurrentUser:
    return CurrentUser(id=TEST_USER_ID, email="test@example.com")


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(client: TestClient, current_user: CurrentUser) -> TestClient:
    async def override() -> CurrentUser:
        return current_user

    app.dependency_overrides[get_current_user] = override
    return client

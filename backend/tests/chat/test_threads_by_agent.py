from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import chats

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _Result:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _Query:
    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self.store = store
        self.table = table
        self.filters: dict[str, str] = {}
        self.pending: dict | None = None

    def upsert(self, row: dict, on_conflict: str | None = None) -> _Query:
        self.store.setdefault(self.table, []).append(dict(row))
        return self

    def insert(self, row: dict) -> _Query:
        self.pending = dict(row)
        return self

    def select(self, *_args: object, **_kwargs: object) -> _Query:
        return self

    def eq(self, key: str, value: str) -> _Query:
        self.filters[key] = value
        return self

    def order(self, *_args: object, **_kwargs: object) -> _Query:
        return self

    def execute(self) -> _Result:
        rows = self.store.setdefault(self.table, [])
        if self.pending is not None:
            rows.append(self.pending)
            saved = self.pending
            self.pending = None
            return _Result([saved])
        matched = [
            row
            for row in rows
            if all(row.get(key) == value for key, value in self.filters.items())
        ]
        return _Result(matched)


class _Client:
    def __init__(self) -> None:
        self.store: dict[str, list[dict]] = {}

    def table(self, name: str) -> _Query:
        return _Query(self.store, name)


def test_each_agent_lists_only_its_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    documents = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="documents")
    email = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")

    document_ids = [row["id"] for row in chats.list_threads(USER_ID, "documents")]
    email_ids = [row["id"] for row in chats.list_threads(USER_ID, "email")]

    assert document_ids == [documents["id"]]
    assert email_ids == [email["id"]]
    assert documents["agent"] == "documents"
    assert email["agent"] == "email"


def test_routes_default_to_documents_and_pass_email(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []
    listed: list[str] = []

    def create(user_id: uuid.UUID, email: str, title: str | None = None, agent: str = "documents") -> dict:
        created.append(agent)
        return {
            "id": str(uuid.uuid4()),
            "title": title or "New chat",
            "agent": agent,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }

    def list_threads(user_id: uuid.UUID, agent: str = "documents") -> list[dict]:
        listed.append(agent)
        return []

    monkeypatch.setattr(chats, "create_thread_for_user", create)
    monkeypatch.setattr(chats, "list_threads", list_threads)

    assert authed_client.post("/threads", json={}).status_code == 200
    assert authed_client.post("/threads", json={"agent": "email"}).status_code == 200
    assert authed_client.get("/threads").status_code == 200
    assert authed_client.get("/threads", params={"agent": "email"}).status_code == 200
    assert authed_client.post("/threads", json={"agent": "other"}).status_code == 422

    assert created == ["documents", "email"]
    assert listed == ["documents", "email"]

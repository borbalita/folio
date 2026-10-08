from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import chats, mailboxes

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
        self.count_messages = False
        self.deleting = False

    def upsert(self, row: dict, on_conflict: str | None = None) -> _Query:
        self.store.setdefault(self.table, []).append(dict(row))
        return self

    def insert(self, row: dict) -> _Query:
        self.pending = dict(row)
        return self

    def select(self, columns: str = "*", **_kwargs: object) -> _Query:
        self.count_messages = "chat_messages(count)" in columns
        return self

    def eq(self, key: str, value: str) -> _Query:
        self.filters[key] = value
        return self

    def order(self, *_args: object, **_kwargs: object) -> _Query:
        return self

    def limit(self, _count: int) -> _Query:
        return self

    def delete(self) -> _Query:
        self.deleting = True
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
        if self.deleting:
            self.store[self.table] = [row for row in rows if row not in matched]
            return _Result(matched)
        if self.count_messages:
            messages = self.store.get("chat_messages", [])
            matched = [
                {
                    **row,
                    "chat_messages": [
                        {
                            "count": sum(
                                1 for m in messages if m["thread_id"] == row["id"]
                            )
                        }
                    ],
                }
                for row in matched
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

    documents = chats.create_thread_for_user(
        USER_ID, "owner@example.com", agent="documents"
    )
    email = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")

    document_ids = [row["id"] for row in chats.list_threads(USER_ID, "documents")]
    email_ids = [row["id"] for row in chats.list_threads(USER_ID, "email")]

    assert document_ids == [documents["id"]]
    assert email_ids == [email["id"]]
    assert documents["agent"] == "documents"
    assert email["agent"] == "email"


def test_new_chat_reuses_the_empty_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    first = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")
    again = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")

    assert again["id"] == first["id"]
    assert len(client.store["chat_threads"]) == 1


def test_new_chat_creates_a_thread_once_the_last_has_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    used = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")
    client.store["chat_messages"] = [{"thread_id": used["id"]}]
    fresh = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")

    assert fresh["id"] != used["id"]


def test_titled_thread_is_always_new(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    empty = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")
    titled = chats.create_thread_for_user(
        USER_ID, "owner@example.com", title="Invoices", agent="email"
    )

    assert titled["id"] != empty["id"]
    assert titled["title"] == "Invoices"


def test_delete_removes_an_empty_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    thread = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")

    assert chats.delete_thread_if_empty(uuid.UUID(thread["id"]), USER_ID) is True
    assert client.store["chat_threads"] == []


def test_delete_keeps_a_thread_with_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(chats, "get_admin_client", lambda: client)

    thread = chats.create_thread_for_user(USER_ID, "owner@example.com", agent="email")
    client.store["chat_messages"] = [{"id": "m1", "thread_id": thread["id"]}]

    assert chats.delete_thread_if_empty(uuid.UUID(thread["id"]), USER_ID) is False
    assert len(client.store["chat_threads"]) == 1


def test_delete_route_reports_the_outcome(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def delete(tid: uuid.UUID, uid: uuid.UUID) -> bool:
        calls.append((tid, uid))
        return True

    monkeypatch.setattr(chats, "delete_thread_if_empty", delete)
    monkeypatch.setattr(
        chats,
        "get_thread_for_user",
        lambda tid, uid: {"id": str(tid), "agent": "documents"},
    )

    response = authed_client.delete(f"/threads/{thread_id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert calls == [(thread_id, USER_ID)]


def test_routes_default_to_documents_and_pass_email(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []
    listed: list[str] = []

    def create(
        user_id: uuid.UUID,
        email: str,
        title: str | None = None,
        agent: str = "documents",
    ) -> dict:
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
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])

    assert authed_client.post("/threads", json={}).status_code == 200
    assert authed_client.post("/threads", json={"agent": "email"}).status_code == 200
    assert authed_client.get("/threads").status_code == 200
    assert authed_client.get("/threads", params={"agent": "email"}).status_code == 200
    assert authed_client.post("/threads", json={"agent": "other"}).status_code == 422

    assert created == ["documents", "email"]
    assert listed == ["documents", "email"]

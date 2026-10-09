from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langfuse.api import NotFoundError

from evals.langfuse_sync import Payload, plan_sync, sync_dataset


def _payload(question: str) -> Payload:
    return {
        "input": {"question": question},
        "expected_output": {"answerable": True},
        "metadata": {},
    }


class FakeDatasets:
    def __init__(self, items: dict[str, Payload] | None = None) -> None:
        self.items = items
        self.created: list[str] = []

    def get_dataset(self, name: str) -> Any:
        if self.items is None:
            raise NotFoundError(body=None)
        return SimpleNamespace(
            items=[
                SimpleNamespace(id=key, **payload)
                for key, payload in self.items.items()
            ]
        )

    def create_dataset(self, *, name: str, description: str, metadata: Any) -> None:
        self.items = {}

    def create_dataset_item(
        self, *, dataset_name: str, id: str, **payload: Any
    ) -> None:
        assert self.items is not None
        self.items[id] = payload
        self.created.append(id)


def test_plan_sorts_items_into_create_unchanged_and_conflicts() -> None:
    local = {"a": _payload("one"), "b": _payload("two"), "c": _payload("three")}
    remote = {"a": _payload("one"), "b": _payload("changed")}

    plan = plan_sync(local, remote)

    assert (plan.create, plan.unchanged, plan.conflicts) == (["c"], ["a"], ["b"])


def test_first_sync_creates_the_dataset_and_every_item() -> None:
    client = FakeDatasets()

    plan = sync_dataset(client, "email-rag-v1", "v1", {"a": _payload("one")})

    assert plan.create == ["a"]
    assert client.items == {"a": _payload("one")}


def test_rerunning_sync_changes_nothing() -> None:
    client = FakeDatasets({"a": _payload("one")})

    plan = sync_dataset(client, "email-rag-v1", "v1", {"a": _payload("one")})

    assert plan.unchanged == ["a"]
    assert client.created == []


def test_changed_content_is_refused_and_nothing_is_uploaded() -> None:
    client = FakeDatasets({"a": _payload("one")})

    plan = sync_dataset(
        client, "email-rag-v1", "v1", {"a": _payload("edited"), "b": _payload("new")}
    )

    assert plan.conflicts == ["a"]
    assert client.created == []

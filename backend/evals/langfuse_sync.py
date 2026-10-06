"""Upload a data version's case files to version-named Langfuse datasets.

Rerunning is safe: unchanged items are skipped, and an item whose content differs from the
committed case is refused, since a synced version is frozen (changes go into a new version).

Run: uv run python -m evals.langfuse_sync [--version v1]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol

from langfuse.api import NotFoundError

from evals.cases import LabelCase, RagCase
from evals.dataset import (
    DEFAULT_VERSION,
    load_label_cases,
    load_rag_cases,
    load_scenario,
)
from evals.scenario import Scenario
from evals.tracing import eval_tracing

Payload = dict[str, Any]
"""input, expected_output, and metadata of one dataset item."""


class DatasetApi(Protocol):
    """The part of the Langfuse client sync uses, so tests can pass a fake."""

    def get_dataset(self, name: str) -> Any: ...
    def create_dataset(self, *, name: str, description: str, metadata: Any) -> Any: ...
    def create_dataset_item(
        self, *, dataset_name: str, id: str, **payload: Any
    ) -> Any: ...


@dataclass
class SyncPlan:
    create: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def rag_dataset_name(version: str) -> str:
    return f"email-rag-{version}"


def label_dataset_name(version: str) -> str:
    return f"email-labels-{version}"


def item_id(dataset_name: str, case_key: str) -> str:
    return f"{dataset_name}-{case_key}"


def rag_payload(case: RagCase) -> Payload:
    data = case.model_dump(mode="json")
    return {
        "input": {
            key: data[key]
            for key in (
                "question",
                "today",
                "probe_query",
                "probe_filters",
                "user_id",
                "mailbox_id",
            )
        },
        "expected_output": {
            key: data[key]
            for key in ("answerable", "expected_email_keys", "expected_facts")
        },
        "metadata": {
            key: data[key] for key in ("case_id", "kind", "split", "distractor_keys")
        },
    }


def label_payload(case: LabelCase, scenario: Scenario) -> Payload:
    email = next(e for e in scenario.emails if e.key == case.email_key)
    sender = next(s for s in scenario.senders if s.key == email.sender_key)
    return {
        "input": {
            "email_key": case.email_key,
            "from": sender.address,
            "subject": email.subject,
        },
        "expected_output": {"label": case.expected_label},
        "metadata": {"email_key": case.email_key, "split": case.split},
    }


def plan_sync(local: dict[str, Payload], remote: dict[str, Payload]) -> SyncPlan:
    """Compare committed cases with the dataset's items by item ID."""
    plan = SyncPlan()
    for key, payload in local.items():
        if key not in remote:
            plan.create.append(key)
        elif _same(payload, remote[key]):
            plan.unchanged.append(key)
        else:
            plan.conflicts.append(key)
    return plan


def remote_payloads(client: DatasetApi, dataset_name: str) -> dict[str, Payload] | None:
    """Item ID -> payload, or None when the dataset does not exist yet."""
    try:
        dataset = client.get_dataset(dataset_name)
    except NotFoundError:
        return None
    return {
        item.id: {
            "input": item.input,
            "expected_output": item.expected_output,
            "metadata": item.metadata,
        }
        for item in dataset.items
    }


def sync_dataset(
    client: DatasetApi, dataset_name: str, version: str, local: dict[str, Payload]
) -> SyncPlan:
    remote = remote_payloads(client, dataset_name)
    if remote is None:
        client.create_dataset(
            name=dataset_name,
            description=f"Email agent eval cases, data {version} (backend/evals/data/{version})",
            metadata={"version": version},
        )
        remote = {}
    plan = plan_sync(local, remote)
    if plan.conflicts:
        return plan
    for key in plan.create:
        client.create_dataset_item(dataset_name=dataset_name, id=key, **local[key])
    return plan


def local_rag_payloads(version: str) -> dict[str, Payload]:
    name = rag_dataset_name(version)
    return {
        item_id(name, case.case_id): rag_payload(case)
        for case in load_rag_cases(version)
    }


def local_label_payloads(version: str) -> dict[str, Payload]:
    name = label_dataset_name(version)
    scenario = load_scenario(version)
    return {
        item_id(name, case.email_key): label_payload(case, scenario)
        for case in load_label_cases(version)
    }


def _same(local: Payload, remote: Payload) -> bool:
    return all(local[part] == remote.get(part) for part in local)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()

    failed = False
    with eval_tracing() as client:
        for name, local in (
            (rag_dataset_name(args.version), local_rag_payloads(args.version)),
            (label_dataset_name(args.version), local_label_payloads(args.version)),
        ):
            plan = sync_dataset(client, name, args.version, local)
            print(
                f"{name}: {len(plan.create)} created, {len(plan.unchanged)} unchanged, "
                f"{len(plan.conflicts)} conflicting"
            )
            if plan.conflicts:
                failed = True
                print(
                    f"  refused: {', '.join(plan.conflicts)} differ from Langfuse. "
                    f"{args.version} is frozen once synced; put changes into a new version.",
                    file=sys.stderr,
                )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

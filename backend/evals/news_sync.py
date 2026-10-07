"""Freeze the news extraction dataset in Langfuse, back it up, and drop the local copy (plan 003/05).

Langfuse holds the lasting copy (dataset news-extraction-<n>); a private Supabase Storage
bucket holds one JSON backup per version. Like the other datasets, a synced version is
frozen: an unchanged rerun is skipped and a changed item is refused. The local working
folder with the newsletters is deleted only after both copies are in place.

Run: uv run python -m evals.news_sync [--version news-v1] [--keep-local]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from typing import Any, Protocol

from app.database.supabase import get_admin_client
from evals.langfuse_sync import Payload, sync_dataset
from evals.news_data import DEFAULT_NEWS_VERSION, Newsletter, load_newsletters, news_dir
from evals.news_review import REFERENCE_RUN, review_dir
from evals.tracing import eval_tracing

BACKUP_BUCKET = "eval-datasets"


class Storage(Protocol):
    """The part of the Supabase storage client the backup uses, so tests can pass a fake."""

    def list_buckets(self) -> list[Any]: ...
    def create_bucket(
        self, id: str, name: str | None = None, options: Any = None
    ) -> Any: ...
    def from_(self, id: str) -> Any: ...


class BackupConflictError(RuntimeError):
    pass


def dataset_name(version: str) -> str:
    """news-v1 -> news-extraction-v1."""
    return "news-extraction-" + version.removeprefix("news-")


def news_payload(newsletter: Newsletter, expected: dict[str, Any]) -> Payload:
    return {
        "input": {
            "key": newsletter.key,
            "source": newsletter.source,
            "sent_date": newsletter.sent_date.isoformat(),
            "subject": newsletter.subject,
            "body": newsletter.body,
        },
        "expected_output": {
            "items": [
                {"title": item["title"], "url": item["url"], "sponsor": item["sponsor"]}
                for item in expected["items"]
            ]
        },
        "metadata": {
            "key": newsletter.key,
            "review": expected["review"],
            "answer_key_run": REFERENCE_RUN
            if expected["review"] == "reference"
            else None,
            "email_id": newsletter.email_id,
        },
    }


def local_payloads(version: str) -> dict[str, Payload]:
    newsletters = load_newsletters(version)
    expected = json.loads((review_dir(version) / "expected.json").read_text())
    missing = [item.key for item in newsletters if item.key not in expected]
    if missing:
        raise SystemExit(
            f"no expected items for {missing}; run evals.news_review first"
        )
    name = dataset_name(version)
    return {
        f"{name}-{item.key}": news_payload(item, expected[item.key])
        for item in newsletters
    }


def backup(storage: Storage, version: str, payloads: dict[str, Payload]) -> str:
    """Write the dataset once to the private bucket; same content again is a no-op."""
    if not any(bucket.id == BACKUP_BUCKET for bucket in storage.list_buckets()):
        storage.create_bucket(BACKUP_BUCKET, options={"public": False})
    path = f"{dataset_name(version)}.json"
    body = json.dumps(payloads, indent=2, sort_keys=True).encode()
    bucket = storage.from_(BACKUP_BUCKET)
    existing = {entry["name"] for entry in bucket.list()}
    if path in existing:
        if bucket.download(path) != body:
            raise BackupConflictError(
                f"{BACKUP_BUCKET}/{path} exists with different content"
            )
        return f"{BACKUP_BUCKET}/{path} unchanged"
    bucket.upload(path, body, {"content-type": "application/json"})
    return f"{BACKUP_BUCKET}/{path} written"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_NEWS_VERSION)
    parser.add_argument(
        "--keep-local", action="store_true", help="Don't delete the working folder"
    )
    args = parser.parse_args()

    payloads = local_payloads(args.version)
    name = dataset_name(args.version)
    with eval_tracing() as client:
        plan = sync_dataset(
            client,
            name,
            args.version,
            payloads,
            description=(
                f"Real AI newsletters with expected news items ({args.version}); "
                "see docs/02-evaluation/plans/003-news-extraction"
            ),
        )
    print(
        f"{name}: {len(plan.create)} created, {len(plan.unchanged)} unchanged, {len(plan.conflicts)} conflicting"
    )
    if plan.conflicts:
        print(
            f"  refused: {', '.join(plan.conflicts)} differ from Langfuse; {name} is frozen.",
            file=sys.stderr,
        )
        return 1

    try:
        print(backup(get_admin_client().storage, args.version, payloads))
    except BackupConflictError as exc:
        print(exc, file=sys.stderr)
        return 1

    folder = news_dir(args.version).parent
    if args.keep_local:
        print(f"kept {folder}")
    else:
        shutil.rmtree(folder)
        print(f"deleted the local working copy {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from datetime import date
from types import SimpleNamespace

import pytest

from evals import news_sync
from evals.news_data import Newsletter

NEWSLETTER = Newsletter(
    key="n01",
    source="tldr",
    sent_date=date(2026, 9, 1),
    subject="AI news",
    body="Story https://a.example/story",
    email_id="00000000-0000-0000-0000-000000000001",
)


class _Bucket:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def list(self) -> list[dict[str, str]]:
        return [{"name": name} for name in self.files]

    def download(self, path: str) -> bytes:
        return self.files[path]

    def upload(self, path: str, body: bytes, options: dict[str, str]) -> None:
        assert options == {"content-type": "application/json"}
        self.files[path] = body


class _Storage:
    def __init__(self) -> None:
        self.buckets: dict[str, tuple[_Bucket, dict[str, object]]] = {}

    def list_buckets(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(id=name) for name in self.buckets]

    def create_bucket(
        self, id: str, name: str | None = None, options: object = None
    ) -> None:
        self.buckets[id] = (_Bucket(), options)  # type: ignore[assignment]

    def from_(self, id: str) -> _Bucket:
        return self.buckets[id][0]


def test_dataset_name_follows_the_data_version() -> None:
    assert news_sync.dataset_name("news-v1") == "news-extraction-v1"


def test_payload_holds_the_newsletter_and_the_expected_items() -> None:
    expected = {
        "review": "reference",
        "items": [
            {
                "title": "Story",
                "blurb": "b",
                "url": "https://a.example/story",
                "sponsor": False,
            }
        ],
    }

    payload = news_sync.news_payload(NEWSLETTER, expected)

    assert payload["input"]["body"] == NEWSLETTER.body
    assert payload["input"]["sent_date"] == "2026-09-01"
    assert payload["expected_output"] == {
        "items": [
            {"title": "Story", "url": "https://a.example/story", "sponsor": False}
        ]
    }
    assert payload["metadata"]["review"] == "reference"
    assert payload["metadata"]["answer_key_run"] == "gpt-5.5@default"


def test_backup_creates_a_private_bucket_and_is_idempotent() -> None:
    storage = _Storage()
    payloads = {"news-extraction-v1-n01": {"input": {"key": "n01"}}}

    first = news_sync.backup(storage, "news-v1", payloads)
    second = news_sync.backup(storage, "news-v1", payloads)

    bucket, options = storage.buckets["eval-datasets"]
    assert options == {"public": False}
    assert list(bucket.files) == ["news-extraction-v1.json"]
    assert first.endswith("written") and second.endswith("unchanged")


def test_backup_refuses_to_overwrite_a_different_version() -> None:
    storage = _Storage()
    news_sync.backup(storage, "news-v1", {"a": {"input": {"key": "n01"}}})

    with pytest.raises(news_sync.BackupConflictError):
        news_sync.backup(storage, "news-v1", {"a": {"input": {"key": "changed"}}})

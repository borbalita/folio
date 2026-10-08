import uuid
from datetime import UTC, date, datetime

import pytest

from app.config import settings
from app.database.models.email.news_item import NewsItem
from app.database.models.user import User
from ingest.email.news import ExtractedItem
from ingest.email.parse import ParsedMessage
from ingest.email.pipeline import ingest_fetched


def test_sponsor_is_dropped_and_order_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    monkeypatch.setattr(
        "ingest.email.labels.settings.ai_newsletter_domains",
        {"tldrnewsletter.com": "tldr"},
    )
    monkeypatch.setattr("ingest.email.news.settings.email_timezone", "Europe/Berlin")
    items = [
        ExtractedItem(title="Alpha", blurb="First story", url="https://a.example"),
        ExtractedItem(
            title="Sponsor", blurb="Buy this", url="https://ad.example", sponsor=True
        ),
        ExtractedItem(title="Beta", blurb="Second story", url="https://b.example"),
    ]
    embedded: list[str] = []

    def embed(texts: list[str]) -> list[list[float]]:
        embedded.extend(texts)
        return [[0.0] * settings.openai_embedding_dimensions for _ in texts]

    parsed = _parsed(from_address="dan@tldrnewsletter.com")
    session = _MemorySession()
    summary = ingest_fetched(
        session,
        [parsed],
        uidvalidity=1,
        highest_uid=1,
        embed=embed,
        extract=lambda _message: items,
    )
    stored = [row for row in session.added if isinstance(row, NewsItem)]
    assert summary.news_items == 2
    assert [(row.position, row.title, row.url) for row in stored] == [
        (0, "Alpha", "https://a.example"),
        (1, "Beta", "https://b.example"),
    ]
    assert embedded[-2:] == ["Alpha\nFirst story", "Beta\nSecond story"]
    assert stored[0].edition_date == date(2026, 1, 2)
    assert stored[0].source == "tldr"
    assert stored[0].embedding_model == settings.openai_embedding_model
    assert stored[0].embedding_dimensions == settings.openai_embedding_dimensions
    assert session.deleted == session.existing


def test_other_mail_is_not_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    monkeypatch.setattr("ingest.email.labels.settings.ai_newsletter_domains", {})

    def extract(_message: ParsedMessage) -> list[ExtractedItem]:
        raise AssertionError("extractor should not run")

    summary = ingest_fetched(
        _MemorySession(),
        [_parsed(from_address="person@example.com")],
        uidvalidity=1,
        highest_uid=1,
        embed=lambda texts: [[0.0] * settings.openai_embedding_dimensions for _ in texts],
        classifier=lambda _prompt: "other",
        extract=extract,
    )
    assert summary.news_items == 0


def _parsed(*, from_address: str) -> ParsedMessage:
    return ParsedMessage(
        message_id="id@example.com",
        provider_message_id="1",
        folder="INBOX",
        subject="TLDR",
        from_address=from_address,
        from_name="",
        to_addresses=["you@yahoo.com"],
        sent_at=datetime(2026, 1, 1, 23, 30, tzinfo=UTC),
        body="Stories",
    )


class _MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.existing: list[object] = [object()]

    def get(self, model: type, ident: uuid.UUID) -> User | None:
        if model is User:
            return User(id=ident, email="owner@example.com")
        return None

    def scalar(self, _statement: object) -> None:
        return None

    def scalars(self, _statement: object) -> list[object]:
        return list(self.existing)

    def add(self, row: object) -> None:
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()  # type: ignore[attr-defined]
        self.added.append(row)

    def delete(self, row: object) -> None:
        self.deleted.append(row)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

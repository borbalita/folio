import uuid
from datetime import UTC, datetime

from app.config import settings
from app.database.models.email.chunk import EmailChunk
from app.database.models.email.mailbox import Mailbox
from app.database.models.email.message import EmailMessage
from app.database.models.user import User
from ingest.email.parse import ParsedMessage, content_hash
from ingest.email.pipeline import (
    IngestSummary,
    StoredEmail,
    ingest_action,
    ingest_fetched,
)


def _parsed(**overrides: object) -> ParsedMessage:
    values: dict[str, object] = {
        "message_id": "id@example.com",
        "provider_message_id": "4",
        "folder": "INBOX",
        "subject": "Hello",
        "from_address": "from@example.com",
        "to_addresses": ["to@example.com"],
        "sent_at": datetime(2026, 1, 1, tzinfo=UTC),
        "body": "Body text",
    }
    values.update(overrides)
    return ParsedMessage(**values)  # type: ignore[arg-type]


def _stored(**overrides: object) -> StoredEmail:
    parsed = _parsed()
    values: dict[str, object] = {
        "content_hash": content_hash(parsed.body, parsed.subject),
        "embedding_model": settings.openai_embedding_model,
        "embedding_dimensions": settings.openai_embedding_dimensions,
    }
    values.update(overrides)
    return StoredEmail(**values)  # type: ignore[arg-type]


def test_skip_when_hash_model_and_dimensions_match() -> None:
    assert ingest_action(_stored(), _parsed()) == "skip"


def test_reembed_when_any_stored_field_changes() -> None:
    parsed = _parsed()
    assert ingest_action(_stored(content_hash="other"), parsed) == "reembed"
    assert ingest_action(_stored(embedding_model="other-model"), parsed) == "reembed"
    assert ingest_action(_stored(embedding_dimensions=1), parsed) == "reembed"


def test_new_when_message_is_absent() -> None:
    assert ingest_action(None, _parsed()) == "new"


def test_fake_fetch_feeds_the_pipeline(monkeypatch) -> None:
    owner_id = uuid.uuid4()
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", owner_id
    )
    session = _MemorySession()
    parsed = _parsed()
    missing = _parsed(message_id=None, provider_message_id="9", subject="No id")
    summary = ingest_fetched(
        session,
        [parsed, missing],
        uidvalidity=42,
        highest_uid=9,
        embed=lambda texts: [
            [0.0] * settings.openai_embedding_dimensions for _ in texts
        ],
        classifier=lambda _prompt: "other",
    )
    assert summary.fetched == 2
    assert summary.new == 1
    assert summary.missing_message_id == 1
    mailbox = next(row for row in session.added if isinstance(row, Mailbox))
    assert mailbox.sync_cursor == {"uidvalidity": 42, "highest_uid": 9}
    assert mailbox.last_synced_at is not None
    stored = next(row for row in session.added if isinstance(row, EmailMessage))
    assert stored.message_id == parsed.message_id
    assert stored.provider_message_id == "4"
    assert any(isinstance(row, EmailChunk) for row in session.added)


class _MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def get(self, model: type, ident: uuid.UUID) -> User | None:
        if model is User:
            return User(id=ident, email="owner@example.com")
        return None

    def scalar(self, _statement: object) -> None:
        return None

    def add(self, row: object) -> None:
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()  # type: ignore[attr-defined]
        self.added.append(row)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def delete(self, _row: object) -> None:
        return None


def test_summary_lists_the_spec_counts() -> None:
    summary = IngestSummary(fetched=5, skipped=5)
    text = summary.render()
    assert "fetched: 5" in text
    assert "skipped: 5" in text
    assert "re-embedded: 0" in text
    assert "news items: 0" in text
    assert "stories rebuilt: 0" in text

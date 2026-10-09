import uuid
from datetime import UTC, datetime

import pytest

from app.config import settings
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel
from app.database.models.user import User
from ingest.email.parse import ParsedAttachment, ParsedMessage
from ingest.email.pipeline import ingest_fetched


def test_small_pdf_is_stored_and_over_cap_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    monkeypatch.setattr("ingest.email.pipeline.settings.attachment_max_bytes", 8)
    small = b"%PDF-ok"
    large = b"%PDF-too-big"
    parsed = ParsedMessage(
        message_id="id@example.com",
        provider_message_id="4",
        folder="INBOX",
        subject="Invoice",
        from_address="billing@example.com",
        from_name="",
        to_addresses=["you@yahoo.com"],
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        body="Please pay.",
        attachments=(
            ParsedAttachment("invoice.pdf", "application/pdf", small),
            ParsedAttachment("statement.pdf", "application/pdf", large),
        ),
    )
    session = _MemorySession()
    summary = ingest_fetched(
        session,
        [parsed],
        uidvalidity=1,
        highest_uid=4,
        embed=lambda texts: [
            [0.0] * settings.openai_embedding_dimensions for _ in texts
        ],
        classifier=lambda _prompt: "other",
    )
    stored = [row for row in session.added if isinstance(row, EmailAttachment)]
    by_name = {row.filename: row for row in stored}
    assert summary.attachments_saved == 1
    assert summary.attachments_skipped == 1
    assert by_name["invoice.pdf"].content == small
    assert by_name["invoice.pdf"].size_bytes == len(small)
    assert by_name["invoice.pdf"].skipped_reason is None
    assert by_name["statement.pdf"].content is None
    assert by_name["statement.pdf"].size_bytes == len(large)
    assert by_name["statement.pdf"].skipped_reason == "too_large"
    email = next(
        row for row in session.added if getattr(row, "label", None) == EmailLabel.OTHER
    )
    assert email.label == EmailLabel.OTHER


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

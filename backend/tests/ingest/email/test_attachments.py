import uuid
from datetime import UTC, datetime

import pytest

from app.config import settings
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel
from app.database.models.finance.invoice import Invoice
from app.database.models.user import User
from ingest.email.invoices import ExtractedInvoice, InvoiceSource
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
            ParsedAttachment("letter.pdf", "application/pdf", small),
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
        invoice_extract=lambda _source: [],
    )
    stored = [row for row in session.added if isinstance(row, EmailAttachment)]
    by_name = {row.filename: row for row in stored}
    assert summary.attachments_saved == 1
    assert summary.attachments_skipped == 1
    assert by_name["letter.pdf"].content == small
    assert by_name["letter.pdf"].size_bytes == len(small)
    assert by_name["letter.pdf"].skipped_reason is None
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

    def scalars(self, _statement: object) -> list[object]:
        return []

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


def test_invoice_email_gets_its_invoices_extracted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    parsed = ParsedMessage(
        message_id="bill@example.com",
        provider_message_id="5",
        folder="INBOX",
        subject="Invoice",
        from_address="billing@example.com",
        from_name="",
        to_addresses=["you@yahoo.com"],
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        body="Please pay.",
        attachments=(ParsedAttachment("invoice.pdf", "application/pdf", b"%PDF-1"),),
    )
    seen: list[InvoiceSource] = []

    def extract(source: InvoiceSource) -> list[ExtractedInvoice]:
        seen.append(source)
        return [ExtractedInvoice(payee="Stadtwerke", amount=12.5, source_file=1)]

    session = _MemorySession()
    summary = ingest_fetched(
        session,
        [parsed],
        uidvalidity=1,
        highest_uid=5,
        embed=lambda texts: [
            [0.0] * settings.openai_embedding_dimensions for _ in texts
        ],
        classifier=lambda _prompt: "invoice",
        invoice_extract=extract,
    )

    assert [source.files for source in seen] == [[("invoice.pdf", b"%PDF-1")]]
    pdf = next(row for row in session.added if isinstance(row, EmailAttachment))
    [invoice] = [row for row in session.added if isinstance(row, Invoice)]
    assert invoice.attachment_id == pdf.id
    assert invoice.payee == "Stadtwerke"
    assert summary.invoices == 1
    assert summary.invoice_failures == 0


def test_other_email_is_not_sent_for_invoice_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    parsed = ParsedMessage(
        message_id="hi@example.com",
        provider_message_id="6",
        folder="INBOX",
        subject="Hi",
        from_address="friend@example.com",
        from_name="",
        to_addresses=["you@yahoo.com"],
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        body="Hello.",
        attachments=(),
    )

    summary = ingest_fetched(
        _MemorySession(),
        [parsed],
        uidvalidity=1,
        highest_uid=6,
        embed=lambda texts: [
            [0.0] * settings.openai_embedding_dimensions for _ in texts
        ],
        classifier=lambda _prompt: "other",
        invoice_extract=lambda _source: pytest.fail("not an invoice"),
    )

    assert summary.invoices == 0


def _other_with_pdf(filename: str = "document.pdf") -> ParsedMessage:
    return ParsedMessage(
        message_id="doc@example.com",
        provider_message_id="7",
        folder="INBOX",
        subject="Your documents",
        from_address="praxis@example.com",
        from_name="",
        to_addresses=["you@yahoo.com"],
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        body="Attached.",
        attachments=(ParsedAttachment(filename, "application/pdf", b"%PDF-2"),),
    )


def _ingest(session, parsed, extract):
    return ingest_fetched(
        session,
        [parsed],
        uidvalidity=1,
        highest_uid=7,
        embed=lambda texts: [[0.0] * settings.openai_embedding_dimensions for _ in texts],
        classifier=lambda _prompt: "other",
        invoice_extract=extract,
    )


def test_invoice_found_in_the_pdf_of_other_mail_relabels_it(monkeypatch) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    session = _MemorySession()

    summary = _ingest(
        session,
        _other_with_pdf(),
        lambda _source: [ExtractedInvoice(payee="Praxis", amount=45.0, source_file=1)],
    )

    email = next(row for row in session.added if getattr(row, "message_id", None))
    assert email.label == EmailLabel.INVOICE
    [invoice] = [row for row in session.added if isinstance(row, Invoice)]
    assert invoice.payee == "Praxis"
    assert summary.invoices == 1
    assert summary.labels == {"invoice": 1}


def test_other_mail_whose_pdf_holds_no_invoice_stays_other(monkeypatch) -> None:
    monkeypatch.setattr("ingest.email.pipeline.settings.yahoo_email", "you@yahoo.com")
    monkeypatch.setattr(
        "ingest.email.pipeline.settings.email_agent_owner_user_id", uuid.uuid4()
    )
    session = _MemorySession()

    summary = _ingest(session, _other_with_pdf(), lambda _source: [])

    email = next(row for row in session.added if getattr(row, "message_id", None))
    assert email.label == EmailLabel.OTHER
    assert not [row for row in session.added if isinstance(row, Invoice)]
    assert summary.invoices == 0

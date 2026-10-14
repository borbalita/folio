import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel, EmailMessage
from app.database.models.finance.invoice import Invoice
from ingest.email.backfill_invoices import backfill
from ingest.email.invoices import ExtractedInvoice, InvoiceSource


def _email(subject: str) -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        mailbox_id=uuid.uuid4(),
        message_id=f"{subject}@example.com",
        subject=subject,
        from_address="billing@example.com",
        sent_at=datetime(2026, 10, 1, tzinfo=UTC),
        body="Please pay.",
        label=EmailLabel.INVOICE,
    )


class _Session:
    """Answers the backfill's queries from in-memory rows, filtered by bound email ids."""

    def __init__(
        self,
        emails: list[EmailMessage],
        attachments: list[EmailAttachment],
        invoices: list[Invoice],
    ) -> None:
        self.emails = emails
        self.attachments = attachments
        self.invoices = invoices
        self.commits = 0

    def scalars(self, statement) -> list[object]:
        entity = statement.column_descriptions[0]["entity"]
        name = statement.column_descriptions[0]["name"]
        ids = set(statement.compile().params.values())
        if entity is EmailMessage:
            return list(self.emails)
        if entity is Invoice and name == "email_id":
            return [row.email_id for row in self.invoices]
        if entity is Invoice:
            return [row for row in self.invoices if row.email_id in ids]
        return [row for row in self.attachments if row.email_id in ids]

    def add(self, row: Invoice) -> None:
        self.invoices.append(row)

    def delete(self, row: Invoice) -> None:
        self.invoices.remove(row)

    def commit(self) -> None:
        self.commits += 1


def test_default_run_extracts_only_emails_without_invoices() -> None:
    done, todo = _email("done"), _email("todo")
    pdf = EmailAttachment(
        id=uuid.uuid4(),
        email_id=todo.id,
        filename="r.pdf",
        content_type="application/pdf",
        size_bytes=6,
        content=b"%PDF-1",
    )
    existing = Invoice(email_id=done.id, position=0, payee="Done", status="open")
    session = _Session([done, todo], [pdf], [existing])
    seen: list[str] = []

    def extract(source: InvoiceSource) -> list[ExtractedInvoice]:
        seen.append(source.subject)
        assert source.files == [("r.pdf", b"%PDF-1")]
        return [ExtractedInvoice(payee="Stadtwerke", amount=5)]

    counts = backfill(session, everything=False, extract=extract)  # type: ignore[arg-type]

    assert seen == ["todo"]
    assert counts == {"emails": 1, "invoices": 1, "invoice_failures": 0}
    [new] = [row for row in session.invoices if row.email_id == todo.id]
    assert new.attachment_id == pdf.id
    assert session.commits == 1


def test_rerun_of_all_keeps_edited_fields() -> None:
    email = _email("edited")
    edited = Invoice(
        email_id=email.id,
        position=0,
        payee="Owner's payee",
        iban="DE89370400440532013000",
        amount=Decimal("99.00"),
        currency="EUR",
        status="open",
        issues=[],
        edited_fields=["payee", "iban", "amount", "currency"],
    )
    session = _Session([email], [], [edited])

    counts = backfill(
        session,  # type: ignore[arg-type]
        everything=True,
        extract=lambda _source: [
            ExtractedInvoice(payee="Model", iban="XX00", amount=1, currency="USD")
        ],
    )

    assert counts["emails"] == 1
    assert session.invoices == [edited]
    assert edited.payee == "Owner's payee"
    assert edited.iban == "DE89370400440532013000"
    assert edited.amount == Decimal("99.00")
    assert edited.currency == "EUR"
    assert edited.status == "open"

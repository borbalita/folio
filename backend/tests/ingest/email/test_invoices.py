import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from structlog.testing import capture_logs

from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel, EmailMessage
from app.database.models.finance.invoice import Invoice
from app.observability import content_free_instrumentation
from app.trace_export import ContentFreeExporter
from ingest.email.invoices import (
    ExtractedInvoice,
    InvoiceSource,
    extract_invoices,
    extract_with_model,
)

VALID_IBAN = "DE89370400440532013000"


def _email() -> EmailMessage:
    return EmailMessage(
        id=uuid.uuid4(),
        mailbox_id=uuid.uuid4(),
        message_id="bill@example.com",
        subject="Your invoices",
        from_address="billing@example.com",
        sent_at=datetime(2026, 10, 1, tzinfo=UTC),
        body="Two invoices attached.",
        label=EmailLabel.INVOICE,
    )


def _pdf(email: EmailMessage, name: str) -> EmailAttachment:
    return EmailAttachment(
        id=uuid.uuid4(),
        email_id=email.id,
        filename=name,
        content_type="application/pdf",
        size_bytes=8,
        content=b"%PDF-" + name.encode(),
    )


def _invoice(**overrides: object) -> ExtractedInvoice:
    values: dict[str, object] = {
        "payee": "Stadtwerke Lindenstrom",
        "iban": "de89 3704 0044 0532 0130 00",
        "bic": "cobadeffxxx",
        "amount": 42.5,
        "currency": "EUR",
        "invoice_number": "R-1001",
        "reference": "Kd 77 R-1001",
        "invoice_date": date(2026, 9, 30),
        "due_date": date(2026, 10, 14),
        "source_file": 1,
    }
    values.update(overrides)
    return ExtractedInvoice(**values)  # type: ignore[arg-type]


class _Session:
    """Holds one email's invoices; enough of a Session for the extraction step."""

    def __init__(self, invoices: list[Invoice] | None = None) -> None:
        self.invoices = list(invoices or [])

    def scalars(self, _statement: object) -> list[Invoice]:
        return list(self.invoices)

    def add(self, row: Invoice) -> None:
        self.invoices.append(row)

    def delete(self, row: Invoice) -> None:
        self.invoices.remove(row)

    def flush(self) -> None:
        return None


def _rows(session: _Session) -> list[Invoice]:
    return sorted(session.invoices, key=lambda row: row.position)


def test_two_invoices_link_to_the_email_and_their_pdfs() -> None:
    email = _email()
    first, second = _pdf(email, "r-1001.pdf"), _pdf(email, "r-1002.pdf")
    session = _Session()

    outcome = extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [first, second],
        extract=lambda _source: [
            _invoice(),
            _invoice(invoice_number="R-1002", amount=10, source_file=2),
        ],
    )

    rows = _rows(session)
    assert outcome.invoices == 2
    assert not outcome.failed
    assert [row.email_id for row in rows] == [email.id, email.id]
    assert [row.attachment_id for row in rows] == [first.id, second.id]
    assert [row.invoice_number for row in rows] == ["R-1001", "R-1002"]
    assert rows[0].iban == VALID_IBAN
    assert rows[0].bic == "COBADEFFXXX"
    assert rows[0].amount == Decimal("42.50")
    assert rows[0].due_date == date(2026, 10, 14)
    assert [row.status for row in rows] == ["open", "open"]


def test_wrong_iban_checksum_needs_info() -> None:
    email = _email()
    session = _Session()

    extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [_pdf(email, "r.pdf")],
        extract=lambda _source: [_invoice(iban="DE89370400440532013001")],
    )

    [row] = session.invoices
    assert row.status == "needs_info"
    assert row.issues == ["invalid_iban"]


def test_two_model_failures_store_needs_info_and_log() -> None:
    email = _email()
    session = _Session()
    calls = 0

    def failing(_source: InvoiceSource) -> list[ExtractedInvoice]:
        nonlocal calls
        calls += 1
        raise UnexpectedModelBehavior("bad output")

    with capture_logs() as logs:
        outcome = extract_invoices(
            session,  # type: ignore[arg-type]
            email,
            [_pdf(email, "r.pdf")],
            extract=failing,
        )

    assert calls == 2
    assert outcome.failed
    [row] = session.invoices
    assert row.email_id == email.id
    assert row.status == "needs_info"
    assert row.issues == ["extraction_failed"]
    assert row.payee is None
    failures = [entry for entry in logs if entry["event"] == "invoice_extract_failed"]
    assert len(failures) == 1
    assert failures[0]["email_id"] == str(email.id)
    assert failures[0]["error"] == "UnexpectedModelBehavior"


def test_one_failure_is_retried() -> None:
    email = _email()
    session = _Session()
    answers: list[object] = [UnexpectedModelBehavior("bad"), [_invoice()]]

    def flaky(_source: InvoiceSource) -> list[ExtractedInvoice]:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer  # type: ignore[return-value]

    outcome = extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [_pdf(email, "r.pdf")],
        extract=flaky,
    )

    assert not outcome.failed
    assert [row.status for row in session.invoices] == ["open"]


def test_failure_keeps_invoices_already_extracted() -> None:
    email = _email()
    kept = Invoice(email_id=email.id, position=0, payee="Kept", status="open")
    session = _Session([kept])

    def failing(_source: InvoiceSource) -> list[ExtractedInvoice]:
        raise UnexpectedModelBehavior("bad")

    outcome = extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [],
        extract=failing,
    )

    assert outcome.failed
    assert session.invoices == [kept]
    assert kept.payee == "Kept"


def test_no_invoice_found_still_yields_one_needs_info() -> None:
    email = _email()
    session = _Session()

    extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [],
        extract=lambda _source: [],
    )

    [row] = session.invoices
    assert row.status == "needs_info"
    assert row.issues == ["no_invoice_found"]


def test_reextraction_keeps_edited_fields_and_rechecks() -> None:
    email = _email()
    pdf = _pdf(email, "r.pdf")
    edited = Invoice(
        email_id=email.id,
        position=0,
        payee="Owner's payee",
        iban=VALID_IBAN,
        amount=Decimal("99.00"),
        currency="EUR",
        status="open",
        issues=[],
        edited_fields=["payee", "amount"],
    )
    stale = Invoice(email_id=email.id, position=1, payee="Gone", status="open")
    session = _Session([edited, stale])

    extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [pdf],
        extract=lambda _source: [
            _invoice(payee="Model payee", amount=1, iban="DE89370400440532013001")
        ],
    )

    assert session.invoices == [edited]
    assert edited.payee == "Owner's payee"
    assert edited.amount == Decimal("99.00")
    assert edited.iban == "DE89370400440532013001"
    assert edited.attachment_id == pdf.id
    assert edited.status == "needs_info"
    assert edited.issues == ["invalid_iban"]


def test_single_pdf_links_without_a_file_number() -> None:
    email = _email()
    pdf = _pdf(email, "r.pdf")
    session = _Session()

    extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [pdf],
        extract=lambda _source: [_invoice(source_file=None)],
    )

    assert session.invoices[0].attachment_id == pdf.id


def test_source_holds_text_and_only_stored_pdfs() -> None:
    email = _email()
    pdf = _pdf(email, "r.pdf")
    skipped = EmailAttachment(
        id=uuid.uuid4(),
        email_id=email.id,
        filename="huge.pdf",
        content_type="application/pdf",
        size_bytes=99,
        content=None,
        skipped_reason="too_large",
    )
    image = EmailAttachment(
        id=uuid.uuid4(),
        email_id=email.id,
        filename="logo.png",
        content_type="image/png",
        size_bytes=3,
        content=b"png",
    )
    seen: list[InvoiceSource] = []

    def record(source: InvoiceSource) -> list[ExtractedInvoice]:
        seen.append(source)
        return [_invoice()]

    extract_invoices(
        _Session(),  # type: ignore[arg-type]
        email,
        [skipped, image, pdf],
        extract=record,
    )

    [source] = seen
    assert source.subject == "Your invoices"
    assert source.body == "Two invoices attached."
    assert source.files == [("r.pdf", pdf.content)]


def test_model_receives_the_pdfs_as_files(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[list[ModelMessage]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(messages)
        tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool.name,
                    {"invoices": [{"payee": "Stadtwerke", "amount": 12.3}]},
                )
            ]
        )

    monkeypatch.setattr("ingest.email.invoices._model", lambda: FunctionModel(model))
    source = InvoiceSource(
        subject="Rechnung",
        body="Anbei die Rechnung.",
        files=[("a.pdf", b"%PDF-a"), ("b.pdf", b"%PDF-b")],
    )

    [invoice] = extract_with_model(source)

    assert invoice.payee == "Stadtwerke"
    assert invoice.amount == 12.3
    [request] = prompts[0]
    [user] = [part for part in request.parts if isinstance(part, UserPromptPart)]
    content = list(user.content)
    texts = [item for item in content if isinstance(item, str)]
    files = [item for item in content if isinstance(item, BinaryContent)]
    assert any("Rechnung" in text and "Anbei die Rechnung." in text for text in texts)
    assert "File 1: a.pdf" in texts and "File 2: b.pdf" in texts
    assert [(item.data, item.media_type) for item in files] == [
        (b"%PDF-a", "application/pdf"),
        (b"%PDF-b", "application/pdf"),
    ]
    assert content.index("File 1: a.pdf") < content.index(files[0])


def test_no_invoice_found_reuses_the_first_row() -> None:
    email = _email()
    first = Invoice(email_id=email.id, position=0, payee="Old", status="open")
    second = Invoice(email_id=email.id, position=1, payee="Old 2", status="open")
    session = _Session([first, second])

    extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [],
        extract=lambda _source: [],
    )

    assert session.invoices == [first]
    assert first.payee is None
    assert first.status == "needs_info"
    assert first.issues == ["no_invoice_found"]


def test_extraction_call_is_traced_without_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        args = {"invoices": [{"payee": "SECRET-PAYEE", "iban": VALID_IBAN}]}
        return ModelResponse(parts=[ToolCallPart(tool.name, args)])

    monkeypatch.setattr("ingest.email.invoices._model", lambda: FunctionModel(model))
    exported = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ContentFreeExporter(exported)))
    Agent.instrument_all(content_free_instrumentation(provider))
    try:
        extract_with_model(
            InvoiceSource(
                subject="SECRET-SUBJECT",
                body="SECRET-BODY",
                files=[("SECRET-NAME.pdf", b"%PDF-SECRET")],
            )
        )
    finally:
        Agent.instrument_all(False)

    spans = exported.get_finished_spans()
    everything = repr(
        [
            (dict(s.attributes or {}), [dict(e.attributes or {}) for e in s.events])
            for s in spans
        ]
    )
    assert spans
    assert "invoice_extraction" in everything
    for secret in ("SECRET-", VALID_IBAN, "%PDF", "JVBER"):
        assert secret not in everything


def test_reextraction_keeps_a_paid_invoice_paid() -> None:
    email = _email()
    paid = Invoice(
        email_id=email.id,
        position=0,
        status="paid",
        paid_by="owner",
        issues=[],
        edited_fields=[],
    )
    session = _Session([paid])

    extract_invoices(
        session,  # type: ignore[arg-type]
        email,
        [],
        extract=lambda _source: [_invoice(iban=None)],
    )

    assert paid.status == "paid"
    assert paid.issues == ["missing_iban"]


def test_payee_is_the_account_holder_from_the_bank_details() -> None:
    from ingest.email.invoices import INSTRUCTIONS

    payee = ExtractedInvoice.model_fields["payee"].description or ""
    for text in (INSTRUCTIONS, payee):
        assert "account holder" in text.lower()
        assert "bank details" in text.lower()


def test_detection_labels_an_email_whose_pdf_holds_an_invoice() -> None:
    from ingest.email.invoices import detect_invoices

    email = _email()
    email.label = EmailLabel.OTHER
    pdf = _pdf(email, "document.pdf")
    session = _Session()

    outcome = detect_invoices(session, email, [pdf], extract=lambda _s: [_invoice()])

    assert email.label == EmailLabel.INVOICE
    assert outcome is not None and outcome.invoices == 1
    [row] = _rows(session)
    assert (row.status, row.attachment_id) == ("open", pdf.id)


def test_detection_leaves_an_email_without_an_invoice_alone() -> None:
    from ingest.email.invoices import detect_invoices

    email = _email()
    email.label = EmailLabel.OTHER
    session = _Session()

    outcome = detect_invoices(session, email, [_pdf(email, "agb.pdf")], extract=lambda _s: [])

    assert outcome is None
    assert email.label == EmailLabel.OTHER
    assert session.invoices == []


def test_detection_skips_emails_without_a_stored_pdf() -> None:
    from ingest.email.invoices import detect_invoices

    email = _email()
    email.label = EmailLabel.OTHER

    def fail(_source: InvoiceSource) -> list[ExtractedInvoice]:
        raise AssertionError("no PDF, no call")

    assert detect_invoices(_Session(), email, [], extract=fail) is None


def test_detection_after_two_failures_stores_nothing() -> None:
    from ingest.email.invoices import detect_invoices

    email = _email()
    email.label = EmailLabel.OTHER

    def broken(_source: InvoiceSource) -> list[ExtractedInvoice]:
        raise UnexpectedModelBehavior("bad output")

    session = _Session()
    assert detect_invoices(session, email, [_pdf(email, "doc.pdf")], extract=broken) is None
    assert email.label == EmailLabel.OTHER
    assert session.invoices == []


def _must_not_extract(_source: InvoiceSource) -> list[ExtractedInvoice]:
    raise AssertionError("extraction should not run")


def test_invoice_email_the_check_rejects_is_not_extracted() -> None:
    email = _email()
    session = _Session()

    outcome = extract_invoices(
        session, email, [_pdf(email, "notice.pdf")], extract=_must_not_extract, check=lambda _s: False
    )

    # Shown as an invoice email that needs info, like "your bill is ready online".
    [row] = _rows(session)
    assert (row.status, row.issues) == ("needs_info", ["no_invoice_found"])
    assert outcome.failed is False


def test_invoice_email_the_check_accepts_is_extracted() -> None:
    email = _email()
    session = _Session()

    extract_invoices(
        session, email, [_pdf(email, "bill.pdf")], extract=lambda _s: [_invoice()], check=lambda _s: True
    )

    [row] = _rows(session)
    assert row.status == "open"


def test_invoice_email_without_pdf_is_checked_from_its_text() -> None:
    email = _email()
    seen: list[InvoiceSource] = []

    def check(source: InvoiceSource) -> bool:
        seen.append(source)
        return False

    extract_invoices(_Session(), email, [], extract=_must_not_extract, check=check)

    assert [(s.body, s.files) for s in seen] == [(email.body, [])]


def test_a_failing_check_does_not_block_an_invoice_email() -> None:
    email = _email()

    def broken(_source: InvoiceSource) -> bool:
        raise UnexpectedModelBehavior("bad output")

    session = _Session()
    extract_invoices(
        session, email, [_pdf(email, "bill.pdf")], extract=lambda _s: [_invoice()], check=broken
    )

    assert [row.status for row in _rows(session)] == ["open"]


def test_detection_extracts_only_after_the_check_says_yes() -> None:
    from ingest.email.invoices import detect_invoices

    email = _email()
    email.label = EmailLabel.OTHER

    assert detect_invoices(
        _Session(), email, [_pdf(email, "agb.pdf")], extract=_must_not_extract, check=lambda _s: False
    ) is None
    outcome = detect_invoices(
        _Session(), email, [_pdf(email, "doc.pdf")], extract=lambda _s: [_invoice()], check=lambda _s: True
    )
    assert outcome is not None and email.label == EmailLabel.INVOICE


def test_detection_with_a_failing_check_stores_nothing() -> None:
    from ingest.email.invoices import detect_invoices

    email = _email()
    email.label = EmailLabel.OTHER

    def broken(_source: InvoiceSource) -> bool:
        raise UnexpectedModelBehavior("bad output")

    assert detect_invoices(
        _Session(), email, [_pdf(email, "doc.pdf")], extract=_must_not_extract, check=broken
    ) is None
    assert email.label == EmailLabel.OTHER

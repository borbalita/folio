"""Extract payment data from an invoice email and its PDFs into checked `invoices` rows."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel, EmailMessage
from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.finance.invoice_checks import (
    FIELD_NAMES,
    InvoiceFields,
    normalize_iban,
    recheck,
)

log = structlog.get_logger(__name__)

INSTRUCTIONS = (
    "Extract every invoice in this email and its attached PDF files. "
    "One email can hold several invoices, usually one per PDF; return one entry each. "
    "Copy values exactly as printed; leave a field empty when the invoice does not show it. "
    "The payee is the account holder named with the bank details (Kontoinhaber, Empfänger, "
    "account name), since the bank checks that name against the IBAN; use the issuer's name "
    "only when the bank details name no one. The reference is the text to put on the transfer "
    "(Verwendungszweck), if the invoice asks for one. "
    "Return nothing for emails that hold no invoice, such as receipts already paid."
)

PDF_MEDIA_TYPE = "application/pdf"


class ExtractedInvoice(BaseModel):
    payee: str | None = Field(
        default=None,
        description=(
            "Account holder of the IBAN, as printed with the bank details; "
            "the issuer's name only when the bank details name no one."
        ),
    )
    iban: str | None = Field(default=None, description="The payee's IBAN.")
    bic: str | None = Field(default=None, description="The payee's BIC, if shown.")
    amount: float | None = Field(
        default=None, description="Total to pay, as a number, e.g. 1234.56."
    )
    currency: str | None = Field(
        default=None, description="ISO 4217 code, e.g. EUR for €."
    )
    invoice_number: str | None = None
    reference: str | None = Field(
        default=None, description="Payment reference to put on the transfer."
    )
    invoice_date: date | None = None
    due_date: date | None = None
    source_file: int | None = Field(
        default=None, description="Number of the file the invoice is in, if any."
    )


class InvoiceExtraction(BaseModel):
    invoices: list[ExtractedInvoice]


@dataclass(frozen=True, slots=True)
class InvoiceSource:
    subject: str
    body: str
    files: list[tuple[str, bytes]]


@dataclass(frozen=True, slots=True)
class InvoiceOutcome:
    invoices: int
    failed: bool


Extractor = Callable[[InvoiceSource], list[ExtractedInvoice]]


def _model() -> Model:
    return OpenAIResponsesModel(
        settings.invoice_extraction_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )


def extract_with_model(source: InvoiceSource) -> list[ExtractedInvoice]:
    """One structured call. PDFs go as files, so scans work without a PDF library."""
    agent = Agent(
        _model(),
        name="invoice_extraction",
        instructions=INSTRUCTIONS,
        output_type=InvoiceExtraction,
    )
    prompt: list[str | BinaryContent] = [f"Subject: {source.subject}\n\n{source.body}"]
    for number, (filename, content) in enumerate(source.files, start=1):
        prompt.append(f"File {number}: {filename}")
        prompt.append(BinaryContent(data=content, media_type=PDF_MEDIA_TYPE))
    return agent.run_sync(prompt).output.invoices


def extract_invoices(
    session: Session,
    email: EmailMessage,
    attachments: list[EmailAttachment],
    *,
    extract: Extractor | None = None,
) -> InvoiceOutcome:
    """Extract, check and store this email's invoices. Fields the owner edited are kept."""
    pdfs = [attachment for attachment in attachments if _is_stored_pdf(attachment)]
    source = InvoiceSource(
        subject=email.subject,
        body=email.body,
        files=[(pdf.filename, pdf.content) for pdf in pdfs if pdf.content is not None],
    )
    existing = list(
        session.scalars(
            select(Invoice)
            .where(Invoice.email_id == email.id)
            .order_by(Invoice.position)
        )
    )
    extracted = _call_with_retry(extract or extract_with_model, source, email.id)
    if extracted is None:
        if not existing:
            session.add(_placeholder(email.id, "extraction_failed"))
        return InvoiceOutcome(invoices=max(len(existing), 1), failed=True)
    if not extracted:
        return _no_invoice_found(session, email.id, existing)

    by_position = {row.position: row for row in existing}
    for position, item in enumerate(extracted):
        row = by_position.get(position)
        if row is None:
            row = Invoice(email_id=email.id, position=position, edited_fields=[])
            session.add(row)
        _apply(row, _clean(item), _attachment_for(item, pdfs))
    _replace_unedited(session, existing, extracted)
    return InvoiceOutcome(invoices=len(extracted), failed=False)


def detect_invoices(
    session: Session,
    email: EmailMessage,
    attachments: list[EmailAttachment],
    *,
    extract: Extractor | None = None,
) -> InvoiceOutcome | None:
    """For mail not labelled as an invoice: if a stored PDF holds one, relabel and store it.

    The labeller sees only filenames and text, so an invoice in `document.pdf` under a
    short note would be missed. Nothing is stored when no invoice is found.
    """
    pdfs = [attachment for attachment in attachments if _is_stored_pdf(attachment)]
    if not pdfs:
        return None
    source = InvoiceSource(
        subject=email.subject,
        body=email.body,
        files=[(pdf.filename, pdf.content) for pdf in pdfs if pdf.content is not None],
    )
    extracted = _call_with_retry(extract or extract_with_model, source, email.id)
    if not extracted:
        return None
    email.label = EmailLabel.INVOICE
    for position, item in enumerate(extracted):
        row = Invoice(email_id=email.id, position=position, edited_fields=[])
        session.add(row)
        _apply(row, _clean(item), _attachment_for(item, pdfs))
    log.info("invoice_detected_in_pdf", email_id=str(email.id), invoices=len(extracted))
    return InvoiceOutcome(invoices=len(extracted), failed=False)


def _call_with_retry(
    extract: Extractor, source: InvoiceSource, email_id: uuid.UUID
) -> list[ExtractedInvoice] | None:
    for attempt in (1, 2):
        try:
            return extract(source)
        except AgentRunError as exc:
            error = type(exc).__name__
            if attempt == 1:
                log.info("invoice_extract_retry", email_id=str(email_id), error=error)
    log.warning("invoice_extract_failed", email_id=str(email_id), error=error)
    return None


def _replace_unedited(
    session: Session, existing: list[Invoice], extracted: list[ExtractedInvoice]
) -> None:
    """Drop rows past the new list, unless the owner edited them."""
    for row in existing:
        if row.position >= len(extracted) and not row.edited_fields:
            session.delete(row)


def _no_invoice_found(
    session: Session, email_id: uuid.UUID, existing: list[Invoice]
) -> InvoiceOutcome:
    """Keep edited rows; otherwise leave one empty `needs_info` row at position 0."""
    if any(row.edited_fields for row in existing):
        _replace_unedited(session, existing, [])
        return InvoiceOutcome(invoices=len(existing), failed=False)
    first = existing[0] if existing and existing[0].position == 0 else None
    for row in existing:
        if row is not first:
            session.delete(row)
    if first is None:
        session.add(_placeholder(email_id, "no_invoice_found"))
    else:
        for name in FIELD_NAMES:
            setattr(first, name, None)
        first.attachment_id = None
        first.status = InvoiceStatus.NEEDS_INFO
        first.issues = ["no_invoice_found"]
    return InvoiceOutcome(invoices=1, failed=False)


def _placeholder(email_id: uuid.UUID, issue: str) -> Invoice:
    return Invoice(
        email_id=email_id,
        position=0,
        status=InvoiceStatus.NEEDS_INFO,
        issues=[issue],
        edited_fields=[],
    )


def _apply(
    row: Invoice, extracted: InvoiceFields, attachment_id: uuid.UUID | None
) -> None:
    edited = set(row.edited_fields or [])
    for name in FIELD_NAMES:
        if name not in edited:
            setattr(row, name, getattr(extracted, name))
    row.attachment_id = attachment_id
    recheck(row)


def _clean(item: ExtractedInvoice) -> InvoiceFields:
    iban = normalize_iban(item.iban) if item.iban else ""
    amount = (
        Decimal(str(item.amount)).quantize(Decimal("0.01"))
        if item.amount is not None
        else None
    )
    return InvoiceFields(
        payee=_text(item.payee),
        iban=iban or None,
        bic=_text(item.bic.upper()) if item.bic else None,
        amount=amount,
        currency=_text(item.currency.upper()) if item.currency else None,
        invoice_number=_text(item.invoice_number),
        reference=_text(item.reference),
        invoice_date=item.invoice_date,
        due_date=item.due_date,
    )


def _text(value: str | None) -> str | None:
    return value.strip() or None if value else None


def _attachment_for(
    item: ExtractedInvoice, pdfs: list[EmailAttachment]
) -> uuid.UUID | None:
    if item.source_file is not None and 1 <= item.source_file <= len(pdfs):
        return pdfs[item.source_file - 1].id
    if len(pdfs) == 1:
        return pdfs[0].id
    return None


def _is_stored_pdf(attachment: EmailAttachment) -> bool:
    if attachment.content is None:
        return False
    return (
        attachment.content_type == PDF_MEDIA_TYPE
        or attachment.filename.lower().endswith(".pdf")
    )

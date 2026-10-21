"""Extract payment data from an invoice email and its PDFs into checked `invoices` rows."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
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
from app.finance.invoice_edits import mark_paid_per_invoice

log = structlog.get_logger(__name__)

INSTRUCTIONS = (
    "Extract every invoice in this email and its attached PDF files. "
    "One email can hold several invoices, usually one per PDF; return one entry each. "
    "Copy values exactly as printed; leave a field empty when the invoice does not show it. "
    "The payee is the account holder named with the bank details (Kontoinhaber, Empfänger, "
    "account name), since the bank checks that name against the IBAN; use the issuer's name "
    "only when the bank details name no one. The reference is the text to put on the transfer "
    "(Verwendungszweck), if the invoice asks for one. "
    "Extract invoices that are already paid too. "
    "Return nothing for emails that hold no invoice."
)

CHECK_INSTRUCTIONS = (
    "Decide what this email and its attached files hold. "
    "to_pay: an invoice or bill with an amount still to pay. "
    "already_paid: an invoice or receipt that says it is paid, for example prepaid online, "
    "paid by card or PayPal, amount received, or already debited. "
    "online_only: a notice that an invoice is ready elsewhere, such as a portal or a "
    "download link, without the invoice itself. "
    "none: anything else, such as order confirmations, account statements, newsletters, "
    "or terms and conditions."
)

PDF_MEDIA_TYPE = "application/pdf"


Verdict = Literal["to_pay", "already_paid", "online_only", "none"]
# The verdicts that hold an invoice to extract.
EXTRACTABLE = ("to_pay", "already_paid")


class InvoiceCheck(BaseModel):
    verdict: Verdict = Field(description="What the email and its files hold.")


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
Checker = Callable[[InvoiceSource], Verdict]


def _model() -> Model:
    return OpenAIResponsesModel(
        settings.invoice_extraction_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )


def _prompt(source: InvoiceSource) -> list[str | BinaryContent]:
    prompt: list[str | BinaryContent] = [f"Subject: {source.subject}\n\n{source.body}"]
    for number, (filename, content) in enumerate(source.files, start=1):
        prompt.append(f"File {number}: {filename}")
        prompt.append(BinaryContent(data=content, media_type=PDF_MEDIA_TYPE))
    return prompt


def extract_with_model(source: InvoiceSource) -> list[ExtractedInvoice]:
    """One structured call. PDFs go as files, so scans work without a PDF library."""
    agent = Agent(
        _model(),
        name="invoice_extraction",
        instructions=INSTRUCTIONS,
        output_type=InvoiceExtraction,
    )
    return agent.run_sync(_prompt(source)).output.invoices


def check_with_model(source: InvoiceSource) -> Verdict:
    """The cheap model reads the same email and PDFs and only names a verdict."""
    effort = settings.invoice_check_reasoning_effort
    agent = Agent(
        OpenAIResponsesModel(
            settings.invoice_check_model,
            provider=OpenAIProvider(api_key=settings.openai_api_key),
        ),
        name="invoice_check",
        instructions=CHECK_INSTRUCTIONS,
        output_type=InvoiceCheck,
        model_settings=(
            OpenAIResponsesModelSettings(openai_reasoning_effort=effort) if effort else None
        ),
    )
    return agent.run_sync(_prompt(source)).output.verdict


def extract_invoices(
    session: Session,
    email: EmailMessage,
    attachments: list[EmailAttachment],
    *,
    extract: Extractor | None = None,
    check: Checker | None = None,
) -> InvoiceOutcome:
    """Extract, check and store this email's invoices. Fields the owner edited are kept.

    With `check`, a cheap model first names what the email holds. Only an invoice to pay
    or an already paid one is extracted; the latter is stored as paid. An invoice only
    available online, or none at all, is stored as `needs_info` without extraction. A
    failed check extracts anyway.
    """
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
    verdict = _check_with_retry(check, source, email.id) if check is not None else None
    if verdict == "online_only":
        return _no_invoice_found(session, email.id, existing, issue="invoice_online")
    if verdict == "none":
        return _no_invoice_found(session, email.id, existing)
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
        if verdict == "already_paid":
            mark_paid_per_invoice(row, paid_at=email.sent_at)
    _replace_unedited(session, existing, extracted)
    return InvoiceOutcome(invoices=len(extracted), failed=False)


def detect_invoices(
    session: Session,
    email: EmailMessage,
    attachments: list[EmailAttachment],
    *,
    extract: Extractor | None = None,
    check: Checker | None = None,
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
    # Only a clear invoice verdict spends the extraction call here.
    verdict = _check_with_retry(check, source, email.id) if check is not None else "to_pay"
    if verdict not in EXTRACTABLE:
        return None
    extracted = _call_with_retry(extract or extract_with_model, source, email.id)
    if not extracted:
        return None
    email.label = EmailLabel.INVOICE
    for position, item in enumerate(extracted):
        row = Invoice(email_id=email.id, position=position, edited_fields=[])
        session.add(row)
        _apply(row, _clean(item), _attachment_for(item, pdfs))
        if verdict == "already_paid":
            mark_paid_per_invoice(row, paid_at=email.sent_at)
    log.info("invoice_detected_in_pdf", email_id=str(email.id), invoices=len(extracted))
    return InvoiceOutcome(invoices=len(extracted), failed=False)


def _check_with_retry(
    check: Checker, source: InvoiceSource, email_id: uuid.UUID
) -> Verdict | None:
    for attempt in (1, 2):
        try:
            found = check(source)
        except AgentRunError as exc:
            error = type(exc).__name__
            if attempt == 1:
                log.info("invoice_check_retry", email_id=str(email_id), error=error)
            continue
        log.info("invoice_checked", email_id=str(email_id), verdict=found)
        return found
    log.warning("invoice_check_failed", email_id=str(email_id), error=error)
    return None


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
    session: Session,
    email_id: uuid.UUID,
    existing: list[Invoice],
    *,
    issue: str = "no_invoice_found",
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
        session.add(_placeholder(email_id, issue))
    else:
        for name in FIELD_NAMES:
            setattr(first, name, None)
        first.attachment_id = None
        first.status = InvoiceStatus.NEEDS_INFO
        first.issues = [issue]
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

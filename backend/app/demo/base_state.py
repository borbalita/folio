"""The demo user's Finance base state as finished rows, dated from today.

Invoices come from the 003/02 builder with fixed seeds, so the base state looks the same
on every reset; only the dates move with today. No model is called.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.config import settings
from app.database.models.email.attachment import EmailAttachment
from app.database.models.email.message import EmailLabel, EmailMessage
from app.database.models.email.news_item import NewsItem
from app.database.models.email.story import NewsStory
from app.database.models.finance.invoice import Invoice, InvoiceStatus
from app.database.models.finance.invoice_match import (
    InvoiceMatch,
    MatchSource,
    MatchStatus,
)
from app.database.models.finance.transaction import Transaction
from app.demo.accounts import DemoAccounts
from app.demo.catalogue import VENDORS, demo_iban
from app.demo.emails import (
    MONTHS,
    DemoInvoice,
    InvoiceKind,
    draw_invoice,
    invoice_message,
)
from app.demo.news_state import build_news_rows
from app.finance.invoice_edits import PAID_BY_INVOICE, PAID_BY_MATCH
from ingest.email.parse import ParsedMessage, content_hash

Role = Literal["open", "matched", "suggested", "paid_before", "online"]


@dataclass(frozen=True, slots=True)
class BaseInvoice:
    vendor: str
    kind: InvoiceKind
    role: Role
    invoice_days_ago: int
    due_in_days: int
    debit_days_ago: int | None = None


# The spec's table: 2 due soon, 1 overdue, 3 matched, 1 suggested, 1 paid before, 1 online.
BASE_INVOICES: tuple[BaseInvoice, ...] = (
    BaseInvoice("mobilfunk", "normal", "open", 6, 4),
    BaseInvoice("strom", "normal", "open", 10, 3),
    BaseInvoice("fitness", "normal", "open", 20, -6),
    BaseInvoice("hosting", "normal", "matched", 40, -33, debit_days_ago=36),
    BaseInvoice("strom", "normal", "matched", 70, -56, debit_days_ago=60),
    BaseInvoice("zahnarzt", "normal", "matched", 55, -25, debit_days_ago=45),
    # Not yet due, so the list shows exactly one overdue invoice, as in the spec.
    BaseInvoice("handwerk", "normal", "suggested", 8, 12, debit_days_ago=4),
    BaseInvoice("mobilfunk", "already_paid", "paid_before", 35, -25),
    BaseInvoice("hosting", "online_only", "online", 3, 7),
)

SALARY = ("Lindgrün Software GmbH", "0700100020", Decimal("3240.00"))
RENT = ("Hausverwaltung Kranich", "0400223300", Decimal("1150.00"))
SHOPS = (
    "Frischmarkt Lindenstraße",
    "Biomarkt am Ufer",
    "Apotheke am Mehringdamm",
    "Café Nordlicht",
    "Drogerie Weiss",
    "Buchhandlung Seitenwind",
)
# The suggestion's debit shares only a name token with the payee; no IBAN, no reference.
SUGGESTED_COUNTERPARTY = "KAYA BRANDT MALERFACHBETR."
SUGGESTED_REMITTANCE = "Rechnung Flur"


@dataclass(frozen=True, slots=True)
class BaseRows:
    emails: list[EmailMessage]
    attachments: list[EmailAttachment]
    invoices: list[Invoice]
    transactions: list[Transaction]
    matches: list[InvoiceMatch]
    news_emails: list[EmailMessage]
    stories: list[NewsStory]
    news_items: list[NewsItem]

    def groups(self) -> tuple[list, ...]:
        """Rows by table, parents before children; insert each group before the next."""
        return (
            self.emails,
            self.news_emails,
            self.stories,
            self.news_items,
            self.attachments,
            self.invoices,
            self.transactions,
            self.matches,
        )

    def all(self) -> list[object]:
        return [row for group in self.groups() for row in group]


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(
        day, time(hour, minute), tzinfo=ZoneInfo(settings.email_timezone)
    )


def _demo_invoice(spec: BaseInvoice, seed: int, today: date) -> DemoInvoice:
    vendor = next(v for v in VENDORS if v.key == spec.vendor)
    invoice_date = today - timedelta(days=spec.invoice_days_ago)
    # Drawn as of the invoice date, so numbers like 2026-… carry the invoice's year.
    drawn = draw_invoice(random.Random(seed), spec.kind, invoice_date, vendor)
    return replace(
        drawn,
        invoice_date=invoice_date,
        due_date=today + timedelta(days=spec.due_in_days),
        debit_date=invoice_date,
    )


def _email_rows(
    message: ParsedMessage, mailbox_id: uuid.UUID
) -> tuple[EmailMessage, list[EmailAttachment]]:
    email = EmailMessage(
        id=uuid.uuid4(),
        mailbox_id=mailbox_id,
        message_id=message.message_id,
        provider_message_id=message.provider_message_id,
        folder=message.folder,
        subject=message.subject,
        from_address=message.from_address,
        from_name=message.from_name,
        to_addresses=message.to_addresses,
        sent_at=message.sent_at,
        body=message.body,
        label=EmailLabel.INVOICE,
        newsletter_source=None,
        content_hash=content_hash(message.body, message.subject),
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.openai_embedding_dimensions,
    )
    attachments = [
        EmailAttachment(
            id=uuid.uuid4(),
            email_id=email.id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=len(attachment.content),
            content=attachment.content,
            skipped_reason=None,
        )
        for attachment in message.attachments
    ]
    return email, attachments


def _invoice_row(
    demo: DemoInvoice, email: EmailMessage, attachments: list[EmailAttachment]
) -> Invoice:
    if demo.kind == "online_only":
        # What the pipeline stores for an online-only notice: a placeholder to fill in.
        return Invoice(
            id=uuid.uuid4(),
            email_id=email.id,
            position=0,
            status=InvoiceStatus.NEEDS_INFO,
            issues=["invoice_online"],
            edited_fields=[],
        )
    return Invoice(
        id=uuid.uuid4(),
        email_id=email.id,
        attachment_id=attachments[0].id,
        position=0,
        payee=demo.vendor.name,
        iban=demo.iban,
        amount=demo.amount,
        currency="EUR",
        invoice_number=demo.number,
        reference=demo.reference,
        invoice_date=demo.invoice_date,
        due_date=demo.due_date,
        status=InvoiceStatus.OPEN,
        issues=[],
        edited_fields=[],
    )


class _Ledger:
    """Transactions of one build, each with a dedup key unique to the build."""

    def __init__(self, account_id: uuid.UUID) -> None:
        self.account_id = account_id
        self.build = uuid.uuid4().hex
        self.rows: list[Transaction] = []

    def add(
        self,
        day: date,
        amount: Decimal,
        name: str,
        remittance: str,
        iban: str | None = None,
    ) -> Transaction:
        tx = Transaction(
            id=uuid.uuid4(),
            account_id=self.account_id,
            booking_date=day,
            amount=amount,
            currency="EUR",
            counterparty_name=name,
            counterparty_iban=iban,
            remittance=remittance,
            bank_code="demo",
            entry_reference=None,
            dedup_key=f"demo-base:{self.build}:{len(self.rows)}",
            raw={"demo_base": True},
        )
        self.rows.append(tx)
        return tx


def _everyday(ledger: _Ledger, today: date) -> None:
    rng = random.Random(2026)
    for month in range(3):
        start = month * 30
        payday = today - timedelta(days=start + 1)
        month_name = MONTHS[payday.month - 1]
        name, account, amount = SALARY
        ledger.add(
            payday, amount, name, f"Gehalt {month_name}", demo_iban("07001000", account)
        )
        name, account, amount = RENT
        ledger.add(
            today - timedelta(days=start + 3),
            -amount,
            name,
            f"Miete {month_name}",
            demo_iban("04002233", account),
        )
        for _ in range(rng.randint(8, 9)):
            day = today - timedelta(days=start + rng.randint(0, 29))
            price = Decimal(rng.randint(350, 8900)) / 100
            ledger.add(day, -price, rng.choice(SHOPS), "Kartenzahlung")


def build_base_state(
    today: date, accounts: DemoAccounts, *, to_address: str
) -> BaseRows:
    emails: list[EmailMessage] = []
    attachments: list[EmailAttachment] = []
    invoices: list[Invoice] = []
    matches: list[InvoiceMatch] = []
    ledger = _Ledger(accounts.account_id)
    for seed, spec in enumerate(BASE_INVOICES, start=1):
        demo = _demo_invoice(spec, seed, today)
        message = invoice_message(
            demo,
            rng=random.Random(100 + seed),
            to_address=to_address,
            sent_at=_at(demo.invoice_date, 8, 15),
        )
        email, files = _email_rows(message, accounts.mailbox_id)
        invoice = _invoice_row(demo, email, files)
        emails.append(email)
        attachments += files
        invoices.append(invoice)
        if spec.role == "paid_before":
            invoice.status = InvoiceStatus.PAID
            invoice.paid_by = PAID_BY_INVOICE
            invoice.paid_at = email.sent_at
            # The debit the invoice announces; unlinked, as the app links only
            # invoices it marks paid by match.
            ledger.add(
                demo.debit_date,
                -demo.amount,
                demo.vendor.name,
                demo.reference,
                demo.iban,
            )
        elif spec.role in ("matched", "suggested"):
            assert spec.debit_days_ago is not None
            debit_day = today - timedelta(days=spec.debit_days_ago)
            if spec.role == "matched":
                tx = ledger.add(
                    debit_day, -demo.amount, demo.vendor.name, demo.reference, demo.iban
                )
                invoice.status = InvoiceStatus.PAID
                invoice.paid_by = PAID_BY_MATCH
                invoice.paid_at = _at(debit_day, 12)
                status, found = MatchStatus.LINKED, ["amount", "iban", "reference"]
            else:
                tx = ledger.add(
                    debit_day,
                    -demo.amount,
                    SUGGESTED_COUNTERPARTY,
                    SUGGESTED_REMITTANCE,
                )
                status, found = MatchStatus.SUGGESTED, ["amount", "name"]
            matches.append(
                InvoiceMatch(
                    id=uuid.uuid4(),
                    invoice_id=invoice.id,
                    transaction_id=tx.id,
                    status=status,
                    source=MatchSource.AUTO,
                    signals=found,
                )
            )
    _everyday(ledger, today)
    news = build_news_rows(today, accounts, to_address=to_address)
    return BaseRows(
        emails,
        attachments,
        invoices,
        ledger.rows,
        matches,
        news.emails,
        news.stories,
        news.items,
    )

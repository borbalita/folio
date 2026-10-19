"""Which notifications are due: pure decisions over invoices, stories and keys already recorded."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Kind = Literal["invoice_new", "invoice_due", "news_big"]
Status = Literal["pending", "skipped"]

DUE_SOON_DAYS = 3
SOURCE_NAMES = {"tldr": "TLDR", "alpha_signal": "Alpha Signal"}


@dataclass(frozen=True)
class InvoiceFacts:
    id: uuid.UUID
    email_id: uuid.UUID
    status: str
    payee: str | None
    amount: Decimal | None
    currency: str | None
    due_date: date | None
    sender: str


@dataclass(frozen=True)
class NewsItemFacts:
    id: uuid.UUID
    source: str
    title: str
    blurb: str
    url: str


@dataclass(frozen=True)
class StoryFacts:
    """A big story's items, oldest first."""

    items: list[NewsItemFacts]


@dataclass(frozen=True)
class NewNotification:
    key: str
    kind: Kind
    status: Status
    text: str


def format_amount(amount: Decimal | None, currency: str | None) -> str:
    if amount is None:
        return "amount unknown"
    if currency == "EUR":
        return f"€{amount:.2f}"
    return f"{amount:.2f} {currency or ''}".strip()


def format_day(day: date) -> str:
    return f"{day.day} {day:%b}"


def _due_soon(invoice: InvoiceFacts, today: date) -> bool:
    if invoice.status != "open" or invoice.due_date is None:
        return False
    return 0 <= (invoice.due_date - today).days <= DUE_SOON_DAYS


def _invoice_link(invoice: InvoiceFacts, app_url: str) -> str:
    return f"{app_url}/finance/invoices/{invoice.email_id}"


def new_invoice_text(invoice: InvoiceFacts, today: date, app_url: str) -> str:
    if invoice.status == "needs_info":
        head = f"🧾 New invoice from {invoice.sender}: details missing, check it in Folio"
    else:
        due = f", due {format_day(invoice.due_date)}" if invoice.due_date else ""
        soon = " · due soon" if _due_soon(invoice, today) else ""
        head = (
            f"🧾 New invoice: {invoice.payee or invoice.sender}, "
            f"{format_amount(invoice.amount, invoice.currency)}{due}{soon}"
        )
    return f"{head}\n{_invoice_link(invoice, app_url)}"


def due_soon_text(invoice: InvoiceFacts, today: date, app_url: str) -> str:
    assert invoice.due_date is not None
    days = (invoice.due_date - today).days
    when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
    return (
        f"⏰ Due {when}: {invoice.payee or invoice.sender}, "
        f"{format_amount(invoice.amount, invoice.currency)} ({format_day(invoice.due_date)})\n"
        f"{_invoice_link(invoice, app_url)}"
    )


def news_links(items: list[NewsItemFacts]) -> str:
    """One link per newsletter, in the order the items came."""
    seen: dict[str, str] = {}
    for item in items:
        seen.setdefault(item.source, item.url)
    return " · ".join(f"{SOURCE_NAMES.get(source, source)}: {url}" for source, url in seen.items())


def news_fallback_text(items: list[NewsItemFacts]) -> str:
    return f"📰 {items[0].title}\n{news_links(items)}"


def plan_notifications(
    invoices: list[InvoiceFacts],
    stories: list[StoryFacts],
    known_keys: set[str],
    *,
    today: date,
    app_url: str,
    enabled: bool,
) -> list[NewNotification]:
    """New rows for events not yet recorded. Each event's key is recorded once, ever."""
    rows: list[NewNotification] = []

    def add(key: str, kind: Kind, status: Status, text: str) -> None:
        if key in known_keys:
            return
        known_keys.add(key)
        rows.append(NewNotification(key, kind, status if enabled else "skipped", text))

    for invoice in invoices:
        new_key = f"invoice_new:{invoice.id}"
        due_key = f"invoice_due:{invoice.id}"
        if new_key not in known_keys:
            # An invoice that arrives paid needs nothing from the owner.
            status: Status = "skipped" if invoice.status == "paid" else "pending"
            add(new_key, "invoice_new", status, new_invoice_text(invoice, today, app_url))
            if _due_soon(invoice, today):
                # The new-invoice message already says "due soon": one message, not two.
                add(due_key, "invoice_due", "skipped", "")
        elif _due_soon(invoice, today):
            add(due_key, "invoice_due", "pending", due_soon_text(invoice, today, app_url))

    for story in stories:
        # Stories are rebuilt with new ids, so "announced" is remembered per news item.
        announced = any(f"news:{item.id}" in known_keys for item in story.items)
        for index, item in enumerate(story.items):
            if index == 0 and not announced:
                add(f"news:{item.id}", "news_big", "pending", news_fallback_text(story.items))
            else:
                add(f"news:{item.id}", "news_big", "skipped", "")
    return rows

"""Read the facts detection needs and record the notifications it plans."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models.email.message import EmailMessage
from app.database.models.email.news_item import NewsItem
from app.database.models.email.story import NewsStory
from app.database.models.finance.invoice import Invoice
from app.database.models.notification import Notification
from app.notifications.detect import (
    InvoiceFacts,
    NewNotification,
    NewsItemFacts,
    StoryFacts,
    plan_notifications,
)


def telegram_enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id and settings.app_url)


def invoice_facts(invoice: Invoice, sender: str) -> InvoiceFacts:
    return InvoiceFacts(
        id=invoice.id,
        email_id=invoice.email_id,
        status=invoice.status,
        payee=invoice.payee,
        amount=invoice.amount,
        currency=invoice.currency,
        due_date=invoice.due_date,
        sender=sender,
    )


def load_invoices(session: Session) -> list[InvoiceFacts]:
    rows = session.execute(
        select(Invoice, EmailMessage.from_address)
        .join(EmailMessage, EmailMessage.id == Invoice.email_id)
        .order_by(EmailMessage.sent_at, Invoice.position)
    ).all()
    return [invoice_facts(row.Invoice, row.from_address) for row in rows]


def load_big_stories(session: Session) -> list[StoryFacts]:
    rows = session.execute(
        select(NewsItem)
        .join(NewsStory, NewsStory.id == NewsItem.story_id)
        .where(NewsStory.is_big.is_(True))
        .order_by(NewsStory.first_seen, NewsItem.edition_date, NewsItem.position)
    ).scalars()
    stories: dict[object, list[NewsItemFacts]] = {}
    for item in rows:
        stories.setdefault(item.story_id, []).append(
            NewsItemFacts(
                id=item.id, source=item.source, title=item.title, blurb=item.blurb, url=item.url
            )
        )
    return [StoryFacts(items=items) for items in stories.values()]


def known_keys(session: Session) -> set[str]:
    return set(session.scalars(select(Notification.key)))


def insert_rows(session: Session, rows: list[NewNotification]) -> None:
    if not rows:
        return
    session.execute(
        insert(Notification)
        .values(
            [
                {"key": row.key, "kind": row.kind, "status": row.status, "text": row.text}
                for row in rows
            ]
        )
        .on_conflict_do_nothing(index_elements=["key"])
    )


def record_notifications(session: Session, now: datetime) -> int:
    """Record notifications for events not seen before; returns how many were planned."""
    today = now.astimezone(ZoneInfo(settings.email_timezone)).date()
    rows = plan_notifications(
        load_invoices(session),
        load_big_stories(session),
        known_keys(session),
        today=today,
        app_url=settings.app_url or "",
        enabled=telegram_enabled(),
    )
    insert_rows(session, rows)
    session.commit()
    return len(rows)

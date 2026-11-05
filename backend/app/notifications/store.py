"""Read the facts detection needs and record the notifications it plans."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.email.message import EmailMessage
from app.database.models.email.news_item import NewsItem
from app.database.models.email.news_item_note import NewsItemNote
from app.database.models.email.story import NewsStory
from app.database.models.finance.invoice import Invoice
from app.database.models.notification import Notification
from app.notifications import security, summary
from app.notifications.detect import (
    InvoiceFacts,
    NewNotification,
    NewsItemFacts,
    StoryFacts,
    plan_notifications,
)
from app.notifications.security import Candidate, Classification

NEWS_LOOKBACK = timedelta(days=2)
ALERT_HISTORY = timedelta(days=7)
ALERT_STATUSES = ("new", "update")


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
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .where(Mailbox.provider != MailboxProvider.DEMO)
        .order_by(EmailMessage.sent_at, Invoice.position)
    ).all()
    return [invoice_facts(row.Invoice, row.from_address) for row in rows]


def _notes_of(item: type[NewsItem]):
    """Join condition to an item's note: by newsletter and position, which survive re-embedding."""
    return and_(NewsItemNote.email_id == item.email_id, NewsItemNote.position == item.position)


def load_stories(session: Session, since: date) -> list[StoryFacts]:
    """Stories seen since `since` that are big or have a security alert: a backfill of old mail
    never announces old news."""
    alerted = (
        select(NewsItem.story_id)
        .join(NewsItemNote, _notes_of(NewsItem))
        .where(NewsItemNote.alert_status.in_(ALERT_STATUSES))
    )
    rows = session.execute(
        select(NewsItem, NewsStory.is_big, NewsItemNote.alert_status)
        .join(NewsStory, NewsStory.id == NewsItem.story_id)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .outerjoin(NewsItemNote, _notes_of(NewsItem))
        .where(
            NewsStory.last_seen >= since,
            Mailbox.provider != MailboxProvider.DEMO,
            or_(NewsStory.is_big.is_(True), NewsStory.id.in_(alerted)),
        )
        .order_by(NewsStory.first_seen, NewsItem.edition_date, NewsItem.position)
    ).all()
    items: dict[object, list[NewsItemFacts]] = {}
    big: dict[object, bool] = {}
    for row in rows:
        item = row.NewsItem
        big[item.story_id] = bool(row.is_big)
        items.setdefault(item.story_id, []).append(
            NewsItemFacts(
                id=item.id,
                email_id=item.email_id,
                position=item.position,
                source=item.source,
                title=item.title,
                blurb=item.blurb,
                url=item.url,
                alert_status=row.alert_status,
            )
        )
    return [StoryFacts(items=found, big=big[story_id]) for story_id, found in items.items()]


def load_unclassified(
    session: Session, since: date, until: date | None = None
) -> list[Candidate]:
    """Non-demo items from [since, until) with no verdict, oldest first.

    Demo items are never classified, so a demo newsletter sends nothing.
    """
    statement = (
        select(NewsItem)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .outerjoin(NewsItemNote, _notes_of(NewsItem))
        .where(
            NewsItem.edition_date >= since,
            Mailbox.provider != MailboxProvider.DEMO,
            NewsItemNote.security.is_(None),
        )
        .order_by(NewsItem.edition_date, NewsItem.source, NewsItem.position)
    )
    if until is not None:
        statement = statement.where(NewsItem.edition_date < until)
    return [
        Candidate(i.email_id, i.position, i.edition_date, i.source, i.title, i.blurb)
        for i in session.execute(statement).scalars().all()
    ]


def load_recent_alerts(session: Session, today: date) -> list[str]:
    """Headlines of the alerts of the last 7 days, for the classifier to compare with."""
    rows = session.execute(
        select(func.coalesce(NewsItemNote.headline, NewsItem.title))
        .select_from(NewsItemNote)
        .join(NewsItem, _notes_of(NewsItem))
        .where(
            NewsItemNote.alert_status.in_(ALERT_STATUSES),
            NewsItem.edition_date >= today - ALERT_HISTORY,
        )
        .order_by(NewsItem.edition_date, NewsItem.position)
    ).all()
    return list(dict.fromkeys(row[0] for row in rows))


def load_editions(session: Session, email_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The whole text of each newsletter the story's items came from."""
    if not email_ids:
        return {}
    rows = session.execute(
        select(EmailMessage.id, EmailMessage.body).where(EmailMessage.id.in_(email_ids))
    ).all()
    return {email_id: body for email_id, body in rows}


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


def explained(session: Session, row: NewNotification) -> tuple[NewNotification, dict | None]:
    """The row with its explained text, and the note to store for the item that carries the key."""
    email_ids = list({item.email_id for item in row.story})
    editions = load_editions(session, email_ids)
    secure = row.kind == "news_security"
    parsed = summary.explain(list(row.story), editions, security=secure)
    text = summary.message(list(row.story), parsed, security=secure, update=row.update)
    if parsed is None:
        return replace(row, text=text), None
    first = row.story[0]
    note = {
        "email_id": first.email_id,
        "position": first.position,
        "headline": parsed.headline.strip(),
        "explanation": parsed.summary.strip(),
    }
    return replace(row, text=text), note


def save_notes(session: Session, notes: list[dict]) -> None:
    if not notes:
        return
    statement = insert(NewsItemNote).values(notes)
    # Only the message's columns: the security columns belong to classification.
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["email_id", "position"],
            set_={
                "headline": statement.excluded.headline,
                "explanation": statement.excluded.explanation,
            },
        )
    )


def save_classifications(session: Session, results: list[Classification]) -> None:
    if not results:
        return
    statement = insert(NewsItemNote).values(
        [
            {
                "email_id": r.email_id,
                "position": r.position,
                "security": r.security,
                "alert_status": r.alert_status,
            }
            for r in results
        ]
    )
    # Only the classification's columns: the headline and explanation belong to the message.
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["email_id", "position"],
            set_={
                "security": statement.excluded.security,
                "alert_status": statement.excluded.alert_status,
            },
        )
    )


def save_security_only(session: Session, results: list[Classification]) -> None:
    """The backfill's write: the mark for the dashboard, never an alert status."""
    if not results:
        return
    statement = insert(NewsItemNote).values(
        [{"email_id": r.email_id, "position": r.position, "security": r.security} for r in results]
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["email_id", "position"],
            set_={"security": statement.excluded.security},
        )
    )


def classify_recent(session: Session, now: datetime) -> int:
    """Classify the last 2 days' items that have no verdict; returns how many were answered.

    A failed call stores nothing, so the next run asks again, and never stops the notifications.
    """
    today = now.astimezone(ZoneInfo(settings.email_timezone)).date()
    candidates = load_unclassified(session, today - NEWS_LOOKBACK)
    if not candidates:
        return 0
    results = security.classify(candidates, load_recent_alerts(session, today))
    if results is None:
        return 0
    save_classifications(session, results)
    session.commit()
    return len(results)


def record_notifications(session: Session, now: datetime) -> int:
    """Record notifications for events not seen before; returns how many were planned."""
    today = now.astimezone(ZoneInfo(settings.email_timezone)).date()
    rows = plan_notifications(
        load_invoices(session),
        load_stories(session, since=today - NEWS_LOOKBACK),
        known_keys(session),
        today=today,
        app_url=settings.app_url or "",
        enabled=telegram_enabled(),
    )
    notes = []
    for index, row in enumerate(rows):
        if row.story and row.status == "pending":
            rows[index], note = explained(session, row)
            if note:
                notes.append(note)
    insert_rows(session, rows)
    save_notes(session, notes)
    session.commit()
    return len(rows)

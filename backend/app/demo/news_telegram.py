"""Send the demo mailbox's most covered big story to Telegram, for the demo video."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_session
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.email.message import EmailMessage
from app.database.models.email.news_item import NewsItem
from app.database.models.email.story import NewsStory
from app.notifications import summary, telegram
from app.notifications.detect import NewsItemFacts

LOOKBACK = timedelta(days=6)


class TelegramNotConfigured(Exception):
    pass


class NoBigStories(Exception):
    pass


def load_demo_stories(
    session: Session, user_id: uuid.UUID
) -> list[list[NewsItemFacts]]:
    """The user's demo-mailbox big stories of the last 7 days, each as its items oldest first."""
    today = datetime.now(ZoneInfo(settings.email_timezone)).date()
    rows = session.execute(
        select(NewsItem, NewsStory.last_seen)
        .join(NewsStory, NewsStory.id == NewsItem.story_id)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .where(
            NewsStory.is_big.is_(True),
            NewsStory.last_seen >= today - LOOKBACK,
            Mailbox.user_id == user_id,
            Mailbox.provider == MailboxProvider.DEMO,
        )
        .order_by(NewsStory.first_seen, NewsItem.edition_date, NewsItem.position)
    ).all()
    stories: dict[object, list[NewsItemFacts]] = {}
    last_seen: dict[object, object] = {}
    for item, seen in rows:
        last_seen[item.story_id] = seen
        stories.setdefault(item.story_id, []).append(
            NewsItemFacts(
                id=item.id,
                email_id=item.email_id,
                position=item.position,
                source=item.source,
                title=item.title,
                blurb=item.blurb,
                url=item.url,
            )
        )
    ranked = sorted(
        stories, key=lambda key: (len(stories[key]), last_seen[key]), reverse=True
    )
    return [stories[key] for key in ranked]


def send_demo_summary(
    user_id: uuid.UUID, *, client: httpx.Client | None = None
) -> dict[str, object]:
    """Summarise the most covered big story like a real news message and post it now.

    Ignores quiet hours and writes no notifications row: it is a one-off for the presenter.
    """
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        raise TelegramNotConfigured
    with get_session() as session:
        stories = load_demo_stories(session, user_id)
    if not stories:
        raise NoBigStories
    items = stories[0]
    text = summary.news_text(items)
    telegram.send_text(text, client=client)
    headline = text.split("\n", 1)[0].removeprefix("📰").strip()
    return {"sent": True, "headline": headline}

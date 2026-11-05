"""The News dashboard's list: a user's newsletter items grouped into stories, by day."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, select

from app.database.engine import get_session
from app.database.models.email.message import EmailMessage
from app.database.models.email.news_item import NewsItem
from app.database.models.email.news_item_note import NewsItemNote
from app.database.models.email.story import NewsStory
from app.notifications.detect import SOURCE_NAMES


@dataclass(frozen=True)
class FeedItem:
    id: uuid.UUID
    email_id: uuid.UUID
    position: int
    source: str
    edition_date: date
    title: str
    blurb: str
    url: str
    story_id: uuid.UUID | None
    is_big: bool
    headline: str | None
    explanation: str | None
    security: bool


def _first_with(items: list[FeedItem], field: str) -> str | None:
    return next((getattr(item, field) for item in items if getattr(item, field)), None)


def _links(items: list[FeedItem]) -> list[dict[str, str]]:
    """One link per newsletter that has one."""
    seen: dict[str, str] = {}
    for item in items:
        if item.url:
            seen.setdefault(item.source, item.url)
    return [
        {"source": source, "name": SOURCE_NAMES.get(source, source), "url": url}
        for source, url in seen.items()
    ]


def _story(items: list[FeedItem]) -> dict[str, Any]:
    """`items` are the story's, oldest first."""
    first = items[0]
    badges = [
        badge
        for badge, marked in (
            ("big", any(item.is_big for item in items)),
            ("security", any(item.security for item in items)),
        )
        if marked
    ]
    return {
        "key": f"{first.email_id}:{first.position}",
        "title": _first_with(items, "headline") or first.title,
        "blurb": max((item.blurb for item in items), key=len),
        "badges": badges,
        "links": _links(items),
        "items": [{"emailId": str(item.email_id), "position": item.position} for item in items],
        "explanation": _first_with(items, "explanation"),
    }


def build_days(
    items: list[FeedItem], *, before: date, days: int, only: str | None = None
) -> list[dict[str, Any]]:
    """Stories whose newest day is in [before - days, before), newest day first.

    A story is placed once, on its newest day, with all its items. Items without a story are
    stories of one.
    """
    start = before - timedelta(days=days)
    by_story: dict[object, list[FeedItem]] = {}
    for item in sorted(items, key=lambda i: (i.edition_date, i.source, i.position)):
        by_story.setdefault(item.story_id or item.id, []).append(item)

    placed: dict[date, list[list[FeedItem]]] = {}
    for story in by_story.values():
        newest = story[-1].edition_date
        if not start <= newest < before:
            continue
        if only == "big" and not any(item.is_big for item in story):
            continue
        if only == "security" and not any(item.security for item in story):
            continue
        placed.setdefault(newest, []).append(story)

    def order(story: list[FeedItem]) -> tuple[int, str, int]:
        # Big first, then security, then where the story sits in its newest day's newsletter.
        on_day = next(item for item in story if item.edition_date == story[-1].edition_date)
        rank = 0 if any(i.is_big for i in story) else 1 if any(i.security for i in story) else 2
        return (rank, on_day.source, on_day.position)

    return [
        {"date": day.isoformat(), "stories": [_story(story) for story in sorted(stories, key=order)]}
        for day, stories in sorted(placed.items(), reverse=True)
    ]


def items_statement(
    mailbox_ids: list[uuid.UUID], *, start: date, before: date
) -> Select[Any]:
    """The user's items of every story that has one in [start, before), all its items."""
    window = (
        select(NewsItem.story_id)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .where(
            EmailMessage.mailbox_id.in_(mailbox_ids),
            NewsItem.edition_date >= start,
            NewsItem.edition_date < before,
            NewsItem.story_id.is_not(None),
        )
    )
    return (
        select(
            NewsItem,
            NewsStory.is_big,
            NewsItemNote.headline,
            NewsItemNote.explanation,
            NewsItemNote.security,
        )
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .outerjoin(NewsStory, NewsStory.id == NewsItem.story_id)
        .outerjoin(
            NewsItemNote,
            and_(
                NewsItemNote.email_id == NewsItem.email_id,
                NewsItemNote.position == NewsItem.position,
            ),
        )
        .where(
            EmailMessage.mailbox_id.in_(mailbox_ids),
            (NewsItem.story_id.in_(window))
            | and_(
                NewsItem.story_id.is_(None),
                NewsItem.edition_date >= start,
                NewsItem.edition_date < before,
            ),
        )
    )


def list_stories(
    mailbox_ids: list[uuid.UUID], *, before: date, days: int, only: str | None
) -> dict[str, Any]:
    start = before - timedelta(days=days)
    with get_session() as session:
        rows = session.execute(items_statement(mailbox_ids, start=start, before=before)).all()
        older = session.scalar(
            select(
                exists().where(
                    NewsItem.email_id == EmailMessage.id,
                    EmailMessage.mailbox_id.in_(mailbox_ids),
                    NewsItem.edition_date < start,
                )
            )
        )
    items = [
        FeedItem(
            id=row.NewsItem.id,
            email_id=row.NewsItem.email_id,
            position=row.NewsItem.position,
            source=row.NewsItem.source,
            edition_date=row.NewsItem.edition_date,
            title=row.NewsItem.title,
            blurb=row.NewsItem.blurb,
            url=row.NewsItem.url,
            story_id=row.NewsItem.story_id,
            is_big=bool(row.is_big),
            headline=row.headline,
            explanation=row.explanation,
            security=bool(row.security),
        )
        for row in rows
    ]
    return {
        "days": build_days(items, before=before, days=days, only=only),
        "nextBefore": start.isoformat() if older else None,
    }

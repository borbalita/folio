"""One newsletter story for a news thread: its items, their edition text, who owns them.

Every statement filters on the user's mailboxes in the query itself, so another user's mail
reads as missing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select, tuple_

from app.database.engine import get_session
from app.database.models.email.message import EmailMessage
from app.database.models.email.news_item import NewsItem
from app.retrieval.news.retriever import NewsPassage

StoryRef = tuple[uuid.UUID, int]

_ITEM_COLUMNS = (
    NewsItem.id,
    NewsItem.story_id,
    NewsItem.email_id,
    NewsItem.position,
    NewsItem.source,
    NewsItem.edition_date,
    NewsItem.title,
    NewsItem.blurb,
    NewsItem.url,
)


@dataclass(frozen=True)
class StoryText:
    item: NewsPassage
    body: str


def _passage(row: Any) -> NewsPassage:
    return NewsPassage(
        item_id=row.id,
        story_id=row.story_id,
        source=row.source,
        edition_date=row.edition_date,
        title=row.title,
        blurb=row.blurb,
        url=row.url,
        score=0.0,
    )


def _scoped(*columns: Any, mailbox_ids: list[uuid.UUID]) -> Select[Any]:
    return (
        select(*columns)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .where(EmailMessage.mailbox_id.in_(mailbox_ids))
    )


def item_statement(mailbox_ids: list[uuid.UUID], item_id: uuid.UUID) -> Select[Any]:
    return _scoped(*_ITEM_COLUMNS, EmailMessage.body, mailbox_ids=mailbox_ids).where(
        NewsItem.id == item_id
    )


def refs_statement(mailbox_ids: list[uuid.UUID], refs: list[StoryRef]) -> Select[Any]:
    """Items by (email, position): those survive re-embedding, item ids do not."""
    return (
        _scoped(*_ITEM_COLUMNS, mailbox_ids=mailbox_ids)
        .where(tuple_(NewsItem.email_id, NewsItem.position).in_(refs))
        .order_by(NewsItem.edition_date, NewsItem.position)
    )


def read_story(mailbox_ids: list[uuid.UUID], item_id: uuid.UUID) -> StoryText | None:
    if not mailbox_ids:
        return None
    with get_session() as session:
        row = session.execute(item_statement(mailbox_ids, item_id)).first()
    return None if row is None else StoryText(item=_passage(row), body=row.body)


def thread_story(mailbox_ids: list[uuid.UUID], refs: list[StoryRef]) -> list[NewsPassage]:
    """The thread's story as its items are now."""
    if not mailbox_ids or not refs:
        return []
    with get_session() as session:
        rows = session.execute(refs_statement(mailbox_ids, refs)).all()
    return [_passage(row) for row in rows]


def owns_all(mailbox_ids: list[uuid.UUID], refs: list[StoryRef]) -> bool:
    """Whether every ref is an item of the user's own mailboxes."""
    return len(thread_story(mailbox_ids, refs)) == len(set(refs))

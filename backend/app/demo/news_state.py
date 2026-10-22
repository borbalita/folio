"""The demo user's AI News as finished rows: newsletter emails, items and stories.

Items and their embeddings come from the committed fixture, so a reset calls no model.
Only the dates move with today.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.database.models.email.message import (
    EmailLabel,
    EmailMessage,
    NewsletterSource,
)
from app.database.models.email.news_item import NewsItem
from app.database.models.email.story import NewsStory
from app.demo.accounts import DemoAccounts
from app.demo.news_fixture import FixtureItem, load_fixture
from ingest.email.parse import content_hash
from ingest.email.stories import is_big

# Pretend issue number of the AI Detective on the epoch day; it counts up daily.
DETECTIVE_EPOCH = date(2026, 1, 1)
DETECTIVE_FIRST_ISSUE = 100


@dataclass(frozen=True, slots=True)
class Newsletter:
    name: str
    from_address: str


NEWSLETTERS = {
    NewsletterSource.DEMO_TENSOR.value: Newsletter(
        "The Daily Tensor", "editors@dailytensor.example"
    ),
    NewsletterSource.DEMO_DETECTIVE.value: Newsletter(
        "AI Detective", "hello@aidetective.example"
    ),
}


@dataclass(frozen=True, slots=True)
class NewsRows:
    emails: list[EmailMessage]
    stories: list[NewsStory]
    items: list[NewsItem]


def _subject(source: str, day: date) -> str:
    if source == NewsletterSource.DEMO_TENSOR.value:
        return f"The Daily Tensor — {day.isoformat()}"
    issue = DETECTIVE_FIRST_ISSUE + (day - DETECTIVE_EPOCH).days
    return f"AI Detective #{issue}"


def _body(items: list[FixtureItem]) -> str:
    return "\n\n".join(f"{i.title}\n{i.blurb}\n{i.url}" for i in items)


def _email(
    source: str,
    day: date,
    items: list[FixtureItem],
    mailbox_id: uuid.UUID,
    to_address: str,
) -> EmailMessage:
    newsletter = NEWSLETTERS[source]
    subject = _subject(source, day)
    body = _body(items)
    message_id = f"<demo-news-{uuid.uuid4()}@folio.example>"
    return EmailMessage(
        id=uuid.uuid4(),
        mailbox_id=mailbox_id,
        message_id=message_id,
        provider_message_id=message_id,
        folder="INBOX",
        subject=subject,
        from_address=newsletter.from_address,
        from_name=newsletter.name,
        to_addresses=[to_address],
        sent_at=datetime.combine(
            day, time(7), tzinfo=ZoneInfo(settings.email_timezone)
        ),
        body=body,
        label=EmailLabel.AI_NEWSLETTER,
        newsletter_source=source,
        content_hash=content_hash(body, subject),
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.openai_embedding_dimensions,
    )


def build_news_rows(
    today: date, accounts: DemoAccounts, *, to_address: str
) -> NewsRows:
    by_edition: dict[tuple[str, int], list[FixtureItem]] = defaultdict(list)
    for fixture_item in load_fixture():
        by_edition[(fixture_item.source, fixture_item.days_ago)].append(fixture_item)

    emails: list[EmailMessage] = []
    items: list[NewsItem] = []
    story_ids: dict[str, uuid.UUID] = {}
    for (source, days_ago), group in sorted(by_edition.items()):
        day = today - timedelta(days=days_ago)
        email = _email(source, day, group, accounts.mailbox_id, to_address)
        emails.append(email)
        for fixture_item in group:
            story_id = story_ids.setdefault(fixture_item.story, uuid.uuid4())
            items.append(
                NewsItem(
                    id=uuid.uuid4(),
                    email_id=email.id,
                    source=source,
                    edition_date=day,
                    position=fixture_item.position,
                    title=fixture_item.title,
                    blurb=fixture_item.blurb,
                    url=fixture_item.url,
                    embedding=fixture_item.embedding,
                    embedding_model=settings.openai_embedding_model,
                    embedding_dimensions=settings.openai_embedding_dimensions,
                    story_id=story_id,
                )
            )

    by_story: dict[uuid.UUID, list[NewsItem]] = defaultdict(list)
    for item in items:
        by_story[item.story_id].append(item)
    stories = [
        NewsStory(
            id=story_id,
            first_seen=min(i.edition_date for i in members),
            last_seen=max(i.edition_date for i in members),
            is_big=is_big(members),
        )
        for story_id, members in by_story.items()
    ]
    return NewsRows(emails, stories, items)

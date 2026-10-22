"""Cluster AI newsletter items into stories. Same-source items are never paired."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import combinations

import structlog
from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from typesafe_sdk import (
    Noul,
    NoulAnswer,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeClient,
)

from app.config import settings
from app.database.models.email.mailbox import Mailbox, MailboxProvider
from app.database.models.email.message import EmailMessage, NewsletterSource
from app.database.models.email.news_item import NewsItem
from app.database.models.email.story import NewsStory

log = structlog.get_logger(__name__)

SameStory = Callable[[NewsItem, NewsItem], bool | None]


def within_window(item_date: date, edition: date, hours: int) -> bool:
    return abs((item_date - edition).days) * 24 <= hours


def cluster_items(
    items: list[NewsItem], same_story: SameStory
) -> tuple[list[list[NewsItem]], list[tuple[NewsItem, NewsItem, bool | None]]]:
    parent = {item.id: item.id for item in items}

    def find(item_id: object) -> object:
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    def union(left_id: object, right_id: object) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root != right_root:
            parent[right_root] = left_root

    decisions: list[tuple[NewsItem, NewsItem, bool | None]] = []
    for left, right in combinations(items, 2):
        if left.source == right.source:
            continue
        answer = same_story(left, right)
        decisions.append((left, right, answer))
        if answer is True:
            union(left.id, right.id)
    groups: dict[object, list[NewsItem]] = defaultdict(list)
    for item in items:
        groups[find(item.id)].append(item)
    return list(groups.values()), decisions


# A story is big when both newsletters of one pair covered it. A user only ever
# has one pair, so the pairs never mix.
NEWSLETTER_PAIRS: tuple[frozenset[str], ...] = (
    frozenset({NewsletterSource.TLDR.value, NewsletterSource.ALPHA_SIGNAL.value}),
    frozenset(
        {NewsletterSource.DEMO_TENSOR.value, NewsletterSource.DEMO_DETECTIVE.value}
    ),
)


def is_big(items: list[NewsItem]) -> bool:
    sources = {item.source for item in items}
    return any(pair <= sources for pair in NEWSLETTER_PAIRS)


@dataclass(frozen=True, slots=True)
class PlannedStory:
    items: list[NewsItem]
    first_seen: date
    last_seen: date
    is_big: bool


def plan_stories(
    items: list[NewsItem],
    edition: date,
    *,
    same_story: SameStory,
    window_hours: int,
) -> tuple[list[PlannedStory], list[tuple[NewsItem, NewsItem, bool | None]]]:
    """Decide story membership. Does not read or write the database."""
    candidates = [
        item
        for item in items
        if within_window(item.edition_date, edition, window_hours)
    ]
    candidate_ids = {item.id for item in candidates}
    touched = {item.story_id for item in candidates if item.story_id is not None}
    outside = [
        item
        for item in items
        if item.story_id in touched and item.id not in candidate_ids
    ]
    groups, decisions = cluster_items(candidates, same_story)
    planned = [_planned(group) for group in groups]
    planned.extend(_planned([item]) for item in outside)
    return planned, decisions


def rebuild_stories(
    session: Session, edition: date, *, same_story: SameStory | None = None
) -> int:
    """Delete stories that touch this edition's window and write them again.

    Stories have no owner, so demo items and the stories only they reference are
    never loaded, replanned or deleted.
    """
    items = [
        row for row in session.scalars(owner_items_query()) if isinstance(row, NewsItem)
    ]
    planned, decisions = plan_stories(
        items,
        edition,
        same_story=same_story or same_story_with_jev,
        window_hours=settings.news_match_window_hours,
    )
    _log_decisions(edition, decisions)
    replaced = {
        item.story_id
        for plan in planned
        for item in plan.items
        if item.story_id is not None
    }
    referenced = {item.story_id for item in items if item.story_id is not None}
    for plan in planned:
        for item in plan.items:
            item.story_id = None
    # Read late (planning calls a model and can take minutes), stories first:
    # a demo reset commits atomically, so a demo story seen here has its items
    # visible to the next read and cannot look orphaned.
    stories = _rows(session, NewsStory)
    demo_referenced = set(session.scalars(demo_story_ids_query()))
    doomed = stories_to_delete(
        [story.id for story in stories],
        replaced=replaced,
        referenced=referenced,
        demo_referenced=demo_referenced,
    )
    for story in stories:
        if story.id in doomed:
            session.delete(story)
    session.flush()
    for plan in planned:
        _add_story(session, plan)
    return len(planned)


def owner_items_query() -> Select:
    return (
        select(NewsItem)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .where(Mailbox.provider != MailboxProvider.DEMO)
    )


def demo_story_ids_query() -> Select:
    return (
        select(NewsItem.story_id)
        .join(EmailMessage, EmailMessage.id == NewsItem.email_id)
        .join(Mailbox, Mailbox.id == EmailMessage.mailbox_id)
        .where(Mailbox.provider == MailboxProvider.DEMO, NewsItem.story_id.is_not(None))
        .distinct()
    )


def stories_to_delete(
    story_ids: list[uuid.UUID],
    *,
    replaced: set[uuid.UUID],
    referenced: set[uuid.UUID],
    demo_referenced: set[uuid.UUID],
) -> set[uuid.UUID]:
    """Replaced stories and orphans go; a story any demo item points at stays."""
    return {
        story_id
        for story_id in story_ids
        if (story_id in replaced or story_id not in referenced)
        and story_id not in demo_referenced
    }


def same_story_with_jev(left: NewsItem, right: NewsItem) -> bool | None:
    state = _pair_prompt(left, right)
    for attempt in (1, 2):
        score = _ask_jev(state)
        if score is not None:
            return score > 0.5
        log.warning("email_same_story_invalid", attempt=attempt)
    return None


def _ask_jev(state: str) -> float | None:
    key = settings.typesafe_api_key
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is required to match news stories")
    try:
        with TypeSafeClient(api_key=key, model=settings.typesafe_label_model) as client:
            result = client.system_one(
                state=state,
                questions={
                    "same_story": Noul(
                        instructions="Are these the same story?",
                        criteria={
                            "true": (
                                "They report the same event, announcement, or development."
                            ),
                            "false": (
                                "They are different stories. A shared topic is not enough."
                            ),
                        },
                    )
                },
            )
    except (TypeSafeAPIError, TypeSafeAPIConnectionError) as exc:
        log.warning("email_same_story_model_error", error=type(exc).__name__)
        return None
    answer = result.answers.get("same_story")
    if not isinstance(answer, NoulAnswer):
        return None
    return answer.noul


def _pair_prompt(left: NewsItem, right: NewsItem) -> str:
    return (
        f"Item A ({left.source})\n"
        f"Title: {left.title}\n"
        f"{left.blurb}\n\n"
        f"Item B ({right.source})\n"
        f"Title: {right.title}\n"
        f"{right.blurb}"
    )


def _rows(session: Session, model: type) -> list:
    return [row for row in session.scalars(select(model)) if isinstance(row, model)]


def _planned(items: list[NewsItem]) -> PlannedStory:
    dates = [item.edition_date for item in items]
    return PlannedStory(
        items=items,
        first_seen=min(dates),
        last_seen=max(dates),
        is_big=is_big(items),
    )


def _add_story(session: Session, planned: PlannedStory) -> None:
    story = NewsStory(
        first_seen=planned.first_seen,
        last_seen=planned.last_seen,
        is_big=planned.is_big,
    )
    session.add(story)
    session.flush()
    for item in planned.items:
        item.story_id = story.id


def _log_decisions(
    edition: date, decisions: list[tuple[NewsItem, NewsItem, bool | None]]
) -> None:
    log.info(
        "email_news_same_story",
        edition=edition.isoformat(),
        checked=len(decisions),
        same=[
            {
                "left_source": left.source,
                "left_title": left.title,
                "right_source": right.source,
                "right_title": right.title,
            }
            for left, right, answer in decisions
            if answer is True
        ],
    )

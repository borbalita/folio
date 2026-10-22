"""list_big_news, catch_up and search_news, scoped to the user's news mailboxes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic_ai import RunContext

from app.config import settings
from app.database import mailboxes
from app.email_assistant.tools.status import emit_status
from app.news_assistant.deps import NewsAgentDeps
from app.retrieval.news.formatting import format_news_passages, format_stories
from app.retrieval.news.queries import NewsSearchFilters
from app.retrieval.news.retriever import Story

READING_NEWSLETTERS = "Reading your AI newsletters"
DEFAULT_DAYS = 7
# Enough for a week of both newsletters, small enough for the model's context.
CATCH_UP_LIMIT = 60


def berlin_today() -> date:
    return datetime.now(ZoneInfo(settings.email_timezone)).date()


async def list_big_news(
    ctx: RunContext[NewsAgentDeps], since: date | None = None, until: date | None = None
) -> str:
    """Big stories (covered by both newsletters), ranked. Without dates: the last 7 days."""
    await emit_status(ctx.deps, READING_NEWSLETTERS)
    return await asyncio.to_thread(
        execute_list_big_news, ctx.deps, since=since, until=until
    )


async def catch_up(
    ctx: RunContext[NewsAgentDeps], since: date | None = None, until: date | None = None
) -> str:
    """A briefing: big stories first, then the other stories, ranked. Without dates: the last 7 days."""
    await emit_status(ctx.deps, READING_NEWSLETTERS)
    return await asyncio.to_thread(execute_catch_up, ctx.deps, since=since, until=until)


async def search_news(
    ctx: RunContext[NewsAgentDeps],
    query: str,
    since: date | None = None,
    until: date | None = None,
    big_only: bool = False,
) -> str:
    """Search newsletter items by topic. Optional since, until, and big_only for big stories only."""
    await emit_status(ctx.deps, READING_NEWSLETTERS)
    return await asyncio.to_thread(
        execute_search_news,
        ctx.deps,
        query,
        since=since,
        until=until,
        big_only=big_only,
    )


def execute_list_big_news(
    deps: NewsAgentDeps, *, since: date | None = None, until: date | None = None
) -> str:
    since, until = _period(since, until)
    stories = deps.news.stories(
        filters=_filters(deps, since=since, until=until, big_only=True),
        limit=settings.retrieval_top_k,
    )
    _remember(deps, stories)
    return format_stories(stories, empty="No big stories in that period.")


def execute_catch_up(
    deps: NewsAgentDeps, *, since: date | None = None, until: date | None = None
) -> str:
    since, until = _period(since, until)
    stories = deps.news.stories(
        filters=_filters(deps, since=since, until=until), limit=CATCH_UP_LIMIT
    )
    _remember(deps, stories)
    return format_stories(stories, empty="No newsletter stories in that period.")


def execute_search_news(
    deps: NewsAgentDeps,
    query: str,
    *,
    since: date | None = None,
    until: date | None = None,
    big_only: bool = False,
) -> str:
    passages = deps.news.search(
        query, filters=_filters(deps, since=since, until=until, big_only=big_only)
    )
    for passage in passages:
        deps.remember(passage.item_id, passage)
    return format_news_passages(passages)


def _period(since: date | None, until: date | None) -> tuple[date | None, date | None]:
    if since is None and until is None:
        until = berlin_today()
        since = until - timedelta(days=DEFAULT_DAYS - 1)
    return since, until


def _remember(deps: NewsAgentDeps, stories: list[Story]) -> None:
    # Items, never stories: a citation must survive the next story rebuild.
    for story in stories:
        for item in story.items:
            deps.remember(item.item_id, item)


def _filters(
    deps: NewsAgentDeps,
    *,
    since: date | None,
    until: date | None,
    big_only: bool = False,
) -> NewsSearchFilters:
    return NewsSearchFilters(
        user_id=deps.user_id,
        mailbox_ids=mailboxes.news_mailbox_ids(deps.user_id),
        since=since,
        until=until,
        big_only=big_only,
    )

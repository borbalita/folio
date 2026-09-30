"""search_news and list_big_news for the email agent."""

from __future__ import annotations

import asyncio
from datetime import date

from pydantic_ai import RunContext

from app.database import mailboxes
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.tools.status import emit_status
from app.retrieval.news.formatting import format_big_stories, format_news_passages
from app.retrieval.news.queries import NewsSearchFilters

READING_NEWSLETTERS = "Reading your AI newsletters"


async def search_news(
    ctx: RunContext[EmailAgentDeps],
    query: str,
    since: date | None = None,
    until: date | None = None,
    big_only: bool = False,
) -> str:
    """Search AI newsletter items by topic. Optional since, until, and big_only for big stories only."""
    await emit_status(ctx.deps, READING_NEWSLETTERS)
    return await asyncio.to_thread(
        execute_search_news,
        ctx.deps,
        query,
        since=since,
        until=until,
        big_only=big_only,
    )


async def list_big_news(
    ctx: RunContext[EmailAgentDeps],
    since: date | None = None,
    until: date | None = None,
) -> str:
    """List big AI news: stories covered by both TLDR and Alpha Signal. Optional since and until."""
    await emit_status(ctx.deps, READING_NEWSLETTERS)
    return await asyncio.to_thread(
        execute_list_big_news, ctx.deps, since=since, until=until
    )


def execute_search_news(
    deps: EmailAgentDeps,
    query: str,
    *,
    since: date | None = None,
    until: date | None = None,
    big_only: bool = False,
) -> str:
    filters = _filters(deps, since=since, until=until, big_only=big_only)
    passages = deps.news.search(query, filters=filters)
    for passage in passages:
        deps.remember(passage.item_id, passage)
    return format_news_passages(passages)


def execute_list_big_news(
    deps: EmailAgentDeps,
    *,
    since: date | None = None,
    until: date | None = None,
) -> str:
    stories = deps.news.big_stories(filters=_filters(deps, since=since, until=until))
    for story in stories:
        for item in story.items:
            deps.remember(item.item_id, item)
    return format_big_stories(stories)


def _filters(
    deps: EmailAgentDeps,
    *,
    since: date | None,
    until: date | None,
    big_only: bool = False,
) -> NewsSearchFilters:
    return NewsSearchFilters(
        user_id=deps.user_id,
        mailbox_ids=mailboxes.active_mailbox_ids(deps.user_id),
        since=since,
        until=until,
        big_only=big_only,
    )

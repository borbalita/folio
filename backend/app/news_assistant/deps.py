"""Per-turn dependencies for the news agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.news.retriever import NewsPassage, NewsRetriever


@dataclass
class NewsAgentDeps:
    user_id: UUID
    thread_id: UUID
    news: NewsRetriever
    seen_ids: set[UUID] = field(default_factory=set)
    seen_passages: dict[UUID, NewsPassage] = field(default_factory=dict)
    status_queue: asyncio.Queue[str | None] | None = None
    # The story a thread was opened from, as (email id, position) refs.
    story_items: list[tuple[UUID, int]] = field(default_factory=list)
    story_title: str | None = None
    # Comparison keys of the URLs this turn's web search returned or opened.
    web_urls: set[str] = field(default_factory=set)

    def remember(self, item_id: UUID, passage: NewsPassage) -> None:
        """Mark an item the model may cite this turn."""
        self.seen_ids.add(item_id)
        self.seen_passages[item_id] = passage

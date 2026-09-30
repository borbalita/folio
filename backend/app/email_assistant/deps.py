"""Per-turn dependencies for the email agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.email.retriever import EmailPassage, EmailRetriever
from app.retrieval.news.retriever import NewsPassage, NewsRetriever


@dataclass
class EmailAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: EmailRetriever
    news: NewsRetriever
    seen_ids: set[UUID] = field(default_factory=set)
    seen_passages: dict[UUID, EmailPassage | NewsPassage] = field(default_factory=dict)
    status_queue: asyncio.Queue[str | None] | None = None

    def remember(self, passage_id: UUID, passage: EmailPassage | NewsPassage) -> None:
        """Mark an id the model may cite this turn."""
        self.seen_ids.add(passage_id)
        self.seen_passages[passage_id] = passage

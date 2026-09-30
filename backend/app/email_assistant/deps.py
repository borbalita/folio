"""Per-turn dependencies for the email agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.email.retriever import EmailPassage, EmailRetriever


@dataclass
class EmailAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: EmailRetriever
    seen_ids: set[UUID] = field(default_factory=set)
    seen_passages: dict[UUID, EmailPassage] = field(default_factory=dict)
    status_queue: asyncio.Queue[str | None] | None = None

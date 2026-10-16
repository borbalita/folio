"""Per-turn dependencies for the finance agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class FinanceAgentDeps:
    user_id: UUID
    thread_id: UUID
    mailbox_ids: list[UUID]
    # Ids a card may show this turn: only what a tool returned.
    seen_invoice_ids: set[UUID] = field(default_factory=set)
    seen_draft_ids: set[UUID] = field(default_factory=set)
    status_queue: asyncio.Queue[str | None] | None = None

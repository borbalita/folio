"""Per-turn dependencies injected into document-agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.retriever import DocumentRetriever, RetrievedPassage


@dataclass
class DocumentAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: DocumentRetriever
    seen_ids: set[UUID] = field(default_factory=set)
    seen_passages: dict[UUID, RetrievedPassage] = field(default_factory=dict)

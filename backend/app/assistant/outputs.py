"""Typed agent output for grounded answers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: UUID
    citation_index: int
    excerpt: str | None = None


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = False


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    answer: GroundedAnswer
    usage: dict[str, int]
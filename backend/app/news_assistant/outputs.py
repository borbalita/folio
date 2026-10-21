"""Typed output for a grounded news answer."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field


class NewsCitationRef(BaseModel):
    chunk_id: UUID = Field(description="The news item id shown in square brackets.")
    citation_index: int
    excerpt: str | None = None


class NewsAnswer(BaseModel):
    answer: str
    citations: list[NewsCitationRef] = Field(default_factory=list)
    insufficient_evidence: bool = False


@dataclass(frozen=True, slots=True)
class NewsTurnResult:
    answer: NewsAnswer
    usage: dict[str, int]

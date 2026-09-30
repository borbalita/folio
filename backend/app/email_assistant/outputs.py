"""Typed output for a grounded email answer."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field


class EmailCitationRef(BaseModel):
    chunk_id: UUID = Field(
        description="The id in square brackets: a mail chunk id or a news item id."
    )
    citation_index: int
    excerpt: str | None = None


class EmailAnswer(BaseModel):
    answer: str
    citations: list[EmailCitationRef] = Field(default_factory=list)
    insufficient_evidence: bool = False


@dataclass(frozen=True, slots=True)
class EmailTurnResult:
    answer: EmailAnswer
    usage: dict[str, int]

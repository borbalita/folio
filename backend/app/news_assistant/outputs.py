"""Typed output for a grounded news answer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field

_PRIVATE_USE = "-"
_CITATION_MARKER = re.compile(
    rf"[ \t]*[{_PRIVATE_USE}]*cite[{_PRIVATE_USE}]*(?:turn\d+[a-z]+\d+[{_PRIVATE_USE}]*)+"
)
_STRAY_PRIVATE_USE = re.compile(f"[{_PRIVATE_USE}]")


def strip_citation_markers(text: str) -> str:
    """Remove the web tool's raw markers, such as citeturn593528view1, from model text."""
    return _STRAY_PRIVATE_USE.sub("", _CITATION_MARKER.sub("", text))


ModelText = Annotated[str, AfterValidator(strip_citation_markers)]


class NewsCitationRef(BaseModel):
    chunk_id: UUID = Field(description="The news item id shown in square brackets.")
    citation_index: int
    excerpt: ModelText | None = None


class WebCitationRef(BaseModel):
    url: str = Field(description="The exact URL of a page searched or opened this turn.")
    title: ModelText = Field(description="A short title for the page.")
    citation_index: int
    excerpt: ModelText | None = None


class NewsAnswer(BaseModel):
    answer: ModelText
    citations: list[NewsCitationRef] = Field(default_factory=list)
    web_citations: list[WebCitationRef] = Field(default_factory=list)
    insufficient_evidence: bool = False


@dataclass(frozen=True, slots=True)
class NewsTurnResult:
    answer: NewsAnswer
    usage: dict[str, int]

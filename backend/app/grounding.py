"""Citation checks against ids retrieved this turn. No LLM."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import ClassVar, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from app.news_assistant.outputs import NewsAnswer

MISSING_CITATIONS = "missing_citations"
UNKNOWN_CHUNK = "unknown_chunk"
DUPLICATE_INDEX = "duplicate_index"
INSUFFICIENT_WITH_CITATIONS = "insufficient_with_citations"


def normalize_url(url: str) -> str | None:
    """A web address's key for comparing citations with sources; None if it isn't one.

    Ignores query string, fragment, scheme, a leading www., host case and a trailing slash.
    Only http and https get a key: ignoring the scheme must not let a javascript: URL match
    a source and reach a link.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"


class GroundingError(Exception):
    """Raised when an answer is not supported by this turn's retrieved ids."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class _Citation(Protocol):
    chunk_id: UUID
    citation_index: int


class _Answer(Protocol):
    citations: Sequence[_Citation]
    insufficient_evidence: bool


class Grounder:
    """The four citation checks. Subclasses supply the canned reply per failure code."""

    user_answers: ClassVar[dict[str, str]]

    def validate(self, answer: _Answer, seen_ids: set[UUID]) -> None:
        if answer.insufficient_evidence:
            if answer.citations:
                raise GroundingError(
                    INSUFFICIENT_WITH_CITATIONS,
                    "Insufficient-evidence answers must not include citations.",
                )
            return

        if not answer.citations:
            raise GroundingError(
                MISSING_CITATIONS,
                "Answers must cite at least one retrieved passage.",
            )

        indexes: set[int] = set()
        for citation in answer.citations:
            if citation.citation_index in indexes:
                raise GroundingError(
                    DUPLICATE_INDEX,
                    f"Duplicate citation_index {citation.citation_index}.",
                )
            indexes.add(citation.citation_index)
            if citation.chunk_id not in seen_ids:
                raise GroundingError(
                    UNKNOWN_CHUNK,
                    f"Citation {citation.chunk_id} was not retrieved in this request.",
                )

    def user_answer(self, exc: GroundingError) -> str:
        return self.user_answers[exc.code]


class DocumentGrounder(Grounder):
    user_answers: ClassVar[dict[str, str]] = {
        MISSING_CITATIONS: (
            "This answer had no cited filing passages, so it is not shown. "
            "Ask about a specific company, fiscal year, or line item in the 10-K corpus."
        ),
        UNKNOWN_CHUNK: (
            "A citation did not match a passage retrieved this turn, so those claims are not shown. "
            "Try the question again, or name a ticker and year."
        ),
        DUPLICATE_INDEX: (
            "The citations on this answer were duplicated, so it is not shown. "
            "Send the question again."
        ),
        INSUFFICIENT_WITH_CITATIONS: (
            "The corpus does not support this question, and the answer also included citations, "
            "so it is not shown. Ask about AAPL, MSFT, NVDA, AMZN, or GOOGL 10-Ks."
        ),
    }


class EmailGrounder(Grounder):
    user_answers: ClassVar[dict[str, str]] = {
        MISSING_CITATIONS: (
            "This answer had no cited mail, so it is not shown. "
            "Ask about a sender, subject, or date."
        ),
        UNKNOWN_CHUNK: (
            "A citation did not match mail retrieved this turn, so those claims are not shown. "
            "Try the question again, or name a sender, subject, or date."
        ),
        DUPLICATE_INDEX: (
            "The citations on this answer were duplicated, so it is not shown. "
            "Send the question again."
        ),
        INSUFFICIENT_WITH_CITATIONS: (
            "The mailbox does not support this question, and the answer also included citations, "
            "so it is not shown."
        ),
    }


class NewsGrounder(Grounder):
    """Item citations are strict. A web citation this turn can't support is only removed."""

    def validate(
        self,
        answer: NewsAnswer,
        seen_ids: set[UUID],
        web_urls: Collection[str] = frozenset(),
    ) -> None:
        had_web_citations = bool(answer.web_citations)
        answer.web_citations = [
            citation
            for citation in answer.web_citations
            if normalize_url(citation.url) in web_urls
        ]
        # An answer whose only citations were web ones stands even if all were removed.
        if answer.citations or not had_web_citations:
            super().validate(answer, seen_ids)
        if answer.web_citations and answer.insufficient_evidence:
            raise GroundingError(
                INSUFFICIENT_WITH_CITATIONS,
                "Insufficient-evidence answers must not include citations.",
            )
        indexes = [
            citation.citation_index
            for citation in (*answer.citations, *answer.web_citations)
        ]
        if len(indexes) != len(set(indexes)):
            raise GroundingError(
                DUPLICATE_INDEX, "An item and a web citation share a citation_index."
            )

    user_answers: ClassVar[dict[str, str]] = {
        MISSING_CITATIONS: (
            "This answer had no cited newsletter items, so it is not shown. "
            "Ask about a period or an AI topic."
        ),
        UNKNOWN_CHUNK: (
            "A citation did not match a newsletter item read this turn, so those claims are "
            "not shown. Try the question again, or name a period or topic."
        ),
        DUPLICATE_INDEX: (
            "The citations on this answer were duplicated, so it is not shown. "
            "Send the question again."
        ),
        INSUFFICIENT_WITH_CITATIONS: (
            "Your newsletters do not cover this question, and the answer also included "
            "citations, so it is not shown."
        ),
    }

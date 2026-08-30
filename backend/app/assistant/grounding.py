"""Citation checks against chunk ids retrieved this turn. No LLM."""

from __future__ import annotations

from uuid import UUID

from app.assistant.outputs import GroundedAnswer


class GroundingError(Exception):
    """Raised when a GroundedAnswer is not supported by this turn's retrieved chunks."""


def validate_grounded_answer(answer: GroundedAnswer, seen_ids: set[UUID]) -> None:
    if answer.insufficient_evidence:
        if answer.citations:
            raise GroundingError(
                "Insufficient-evidence answers must not include citations.",
            )
        return

    if not answer.citations:
        raise GroundingError(
            "Answers must cite at least one retrieved passage.",
        )

    indexes: set[int] = set()
    for citation in answer.citations:
        if citation.citation_index in indexes:
            raise GroundingError(
                f"Duplicate citation_index {citation.citation_index}.",
            )
        indexes.add(citation.citation_index)
        if citation.chunk_id not in seen_ids:
            raise GroundingError(
                f"Citation {citation.chunk_id} was not retrieved in this request.",
            )

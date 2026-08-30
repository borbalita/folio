from __future__ import annotations

from uuid import UUID

import pytest

from app.assistant.grounding import GroundingError, validate_grounded_answer
from app.assistant.outputs import Citation, GroundedAnswer

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")


def _answer(**overrides: object) -> GroundedAnswer:
    values: dict[str, object] = {
        "answer": "Services revenue increased.",
        "citations": [Citation(chunk_id=A, citation_index=1, excerpt="Services revenue increased.")],
        "insufficient_evidence": False,
    }
    values.update(overrides)
    return GroundedAnswer.model_validate(values)


def test_valid_citations_pass() -> None:
    validate_grounded_answer(_answer(), {A, B})


def test_unknown_chunk_is_rejected() -> None:
    with pytest.raises(GroundingError, match="not retrieved"):
        validate_grounded_answer(_answer(), {B})


def test_missing_citations_rejected() -> None:
    with pytest.raises(GroundingError, match="at least one"):
        validate_grounded_answer(_answer(citations=[]), {A})


def test_insufficient_evidence_must_have_no_citations() -> None:
    with pytest.raises(GroundingError, match="must not include citations"):
        validate_grounded_answer(
            _answer(insufficient_evidence=True),
            {A},
        )


def test_insufficient_evidence_with_empty_citations_passes() -> None:
    validate_grounded_answer(
        _answer(insufficient_evidence=True, citations=[]),
        set(),
    )


def test_duplicate_citation_index_rejected() -> None:
    with pytest.raises(GroundingError, match="Duplicate citation_index"):
        validate_grounded_answer(
            _answer(
                citations=[
                    Citation(chunk_id=A, citation_index=1),
                    Citation(chunk_id=B, citation_index=1),
                ],
            ),
            {A, B},
        )

from __future__ import annotations

from uuid import UUID

import pytest

from app.assistant.grounding import (
    DUPLICATE_INDEX,
    INSUFFICIENT_WITH_CITATIONS,
    MISSING_CITATIONS,
    UNKNOWN_CHUNK,
    GroundingError,
    grounding_user_answer,
    validate_grounded_answer,
)
from app.assistant.outputs import Citation, GroundedAnswer

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")

CODES = (
    MISSING_CITATIONS,
    UNKNOWN_CHUNK,
    DUPLICATE_INDEX,
    INSUFFICIENT_WITH_CITATIONS,
)


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
    with pytest.raises(GroundingError, match="not retrieved") as caught:
        validate_grounded_answer(_answer(), {B})
    assert caught.value.code == UNKNOWN_CHUNK


def test_missing_citations_rejected() -> None:
    with pytest.raises(GroundingError, match="at least one") as caught:
        validate_grounded_answer(_answer(citations=[]), {A})
    assert caught.value.code == MISSING_CITATIONS


def test_insufficient_evidence_must_have_no_citations() -> None:
    with pytest.raises(GroundingError, match="must not include citations") as caught:
        validate_grounded_answer(
            _answer(insufficient_evidence=True),
            {A},
        )
    assert caught.value.code == INSUFFICIENT_WITH_CITATIONS


def test_insufficient_evidence_with_empty_citations_passes() -> None:
    validate_grounded_answer(
        _answer(insufficient_evidence=True, citations=[]),
        set(),
    )


def test_duplicate_citation_index_rejected() -> None:
    with pytest.raises(GroundingError, match="Duplicate citation_index") as caught:
        validate_grounded_answer(
            _answer(
                citations=[
                    Citation(chunk_id=A, citation_index=1),
                    Citation(chunk_id=B, citation_index=1),
                ],
            ),
            {A, B},
        )
    assert caught.value.code == DUPLICATE_INDEX


def test_grounding_user_answers_are_not_validator_text() -> None:
    for code in CODES:
        text = grounding_user_answer(GroundingError(code, "Answers must cite at least one retrieved passage."))
        assert text.strip()
        assert "retrieved passage" not in text
        assert "citation_index" not in text
        assert "must not include citations" not in text

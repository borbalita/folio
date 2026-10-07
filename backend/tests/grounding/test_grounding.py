from __future__ import annotations

from uuid import UUID

import pytest

from app.assistant.outputs import GroundedAnswer
from app.email_assistant.outputs import EmailAnswer
from app.grounding import (
    DUPLICATE_INDEX,
    INSUFFICIENT_WITH_CITATIONS,
    MISSING_CITATIONS,
    UNKNOWN_CHUNK,
    DocumentGrounder,
    EmailGrounder,
    Grounder,
    GroundingError,
)

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")

CODES = (
    MISSING_CITATIONS,
    UNKNOWN_CHUNK,
    DUPLICATE_INDEX,
    INSUFFICIENT_WITH_CITATIONS,
)


def _cases(**overrides: object) -> list[tuple[Grounder, GroundedAnswer | EmailAnswer]]:
    values: dict[str, object] = {
        "answer": "Services revenue increased.",
        "citations": [
            {
                "chunk_id": A,
                "citation_index": 1,
                "excerpt": "Services revenue increased.",
            }
        ],
        "insufficient_evidence": False,
    }
    values.update(overrides)
    return [
        (DocumentGrounder(), GroundedAnswer.model_validate(values)),
        (EmailGrounder(), EmailAnswer.model_validate(values)),
    ]


@pytest.mark.parametrize(("grounder", "answer"), _cases())
def test_valid_citations_pass(
    grounder: Grounder, answer: GroundedAnswer | EmailAnswer
) -> None:
    grounder.validate(answer, {A, B})


@pytest.mark.parametrize(("grounder", "answer"), _cases())
def test_unknown_chunk_is_rejected(
    grounder: Grounder, answer: GroundedAnswer | EmailAnswer
) -> None:
    with pytest.raises(GroundingError, match="not retrieved") as caught:
        grounder.validate(answer, {B})
    assert caught.value.code == UNKNOWN_CHUNK


@pytest.mark.parametrize(("grounder", "answer"), _cases(citations=[]))
def test_missing_citations_rejected(
    grounder: Grounder, answer: GroundedAnswer | EmailAnswer
) -> None:
    with pytest.raises(GroundingError, match="at least one") as caught:
        grounder.validate(answer, {A})
    assert caught.value.code == MISSING_CITATIONS


@pytest.mark.parametrize(("grounder", "answer"), _cases(insufficient_evidence=True))
def test_insufficient_evidence_must_have_no_citations(
    grounder: Grounder, answer: GroundedAnswer | EmailAnswer
) -> None:
    with pytest.raises(GroundingError, match="must not include citations") as caught:
        grounder.validate(answer, {A})
    assert caught.value.code == INSUFFICIENT_WITH_CITATIONS


@pytest.mark.parametrize(
    ("grounder", "answer"), _cases(insufficient_evidence=True, citations=[])
)
def test_insufficient_evidence_with_empty_citations_passes(
    grounder: Grounder, answer: GroundedAnswer | EmailAnswer
) -> None:
    grounder.validate(answer, set())


@pytest.mark.parametrize(
    ("grounder", "answer"),
    _cases(
        citations=[
            {"chunk_id": A, "citation_index": 1},
            {"chunk_id": B, "citation_index": 1},
        ]
    ),
)
def test_duplicate_citation_index_rejected(
    grounder: Grounder, answer: GroundedAnswer | EmailAnswer
) -> None:
    with pytest.raises(GroundingError, match="Duplicate citation_index") as caught:
        grounder.validate(answer, {A, B})
    assert caught.value.code == DUPLICATE_INDEX


@pytest.mark.parametrize("grounder", (DocumentGrounder(), EmailGrounder()))
def test_every_code_has_a_user_answer_that_is_not_validator_text(
    grounder: Grounder,
) -> None:
    for code in CODES:
        text = grounder.user_answer(
            GroundingError(code, "Answers must cite at least one retrieved passage.")
        )
        assert text.strip()
        assert "retrieved passage" not in text
        assert "citation_index" not in text
        assert "must not include citations" not in text


def test_email_answers_talk_about_mail() -> None:
    documents = DocumentGrounder().user_answer(GroundingError(MISSING_CITATIONS, ""))
    email = EmailGrounder().user_answer(GroundingError(MISSING_CITATIONS, ""))

    assert "10-K" in documents
    assert "mail" in email

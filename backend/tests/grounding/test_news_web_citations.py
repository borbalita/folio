from __future__ import annotations

from uuid import UUID

import pytest

from app.grounding import (
    DUPLICATE_INDEX,
    INSUFFICIENT_WITH_CITATIONS,
    MISSING_CITATIONS,
    UNKNOWN_CHUNK,
    GroundingError,
    NewsGrounder,
    normalize_url,
)
from app.news_assistant.outputs import NewsAnswer, NewsCitationRef, WebCitationRef

ITEM = UUID("00000000-0000-0000-0000-00000000000a")
SOURCE = normalize_url("https://example.com/report")


def _web(url: str = "https://example.com/report", index: int = 2) -> WebCitationRef:
    return WebCitationRef(url=url, title="Report", citation_index=index, excerpt="text")


def _item(index: int = 1, item_id: UUID = ITEM) -> NewsCitationRef:
    return NewsCitationRef(chunk_id=item_id, citation_index=index, excerpt="text")


def _answer(**fields: object) -> NewsAnswer:
    return NewsAnswer.model_validate({"answer": "It happened.", **fields})


@pytest.mark.parametrize(
    "variant",
    [
        "https://example.com/report?sid=123",
        "https://example.com/report#section",
        "http://example.com/report",
        "https://www.example.com/report",
        "https://EXAMPLE.com/report",
        "https://example.com/report/",
        "HTTPS://WWW.Example.COM/report/?trk=x#top",
    ],
)
def test_urls_compare_ignoring_the_owners_differences(variant: str) -> None:
    assert normalize_url(variant) == SOURCE


@pytest.mark.parametrize(
    "other",
    [
        "https://example.com/other",
        "https://example.com/Report",
        "https://sub.example.com/report",
        "https://example.org/report",
    ],
)
def test_urls_that_really_differ_do_not_match(other: str) -> None:
    assert normalize_url(other) != SOURCE


@pytest.mark.parametrize(
    "url",
    [
        "javascript://example.com/report?%0aalert(1)",
        "data:text/html,hi",
        "example.com/report",
        "https://",
        "http://[broken",
        "",
    ],
)
def test_anything_but_a_web_address_has_no_key(url: str) -> None:
    assert normalize_url(url) is None


def test_a_web_citation_this_turn_did_not_return_is_removed_and_the_answer_kept() -> None:
    answer = _answer(citations=[_item()], web_citations=[_web("https://made.up/page")])

    NewsGrounder().validate(answer, {ITEM}, {SOURCE})

    assert answer.web_citations == []
    assert [citation.chunk_id for citation in answer.citations] == [ITEM]
    assert answer.answer == "It happened."


def test_an_answer_whose_only_citations_were_removed_is_kept() -> None:
    answer = _answer(web_citations=[_web("https://made.up/page")])

    NewsGrounder().validate(answer, set(), {SOURCE})

    assert answer.web_citations == []
    assert answer.answer == "It happened."


def test_only_the_unmatched_web_citation_is_removed() -> None:
    kept = _web(index=1)
    answer = _answer(web_citations=[kept, _web("https://made.up/page", index=2)])

    NewsGrounder().validate(answer, set(), {SOURCE})

    assert answer.web_citations == [kept]


def test_a_web_citation_with_a_noisy_url_is_kept() -> None:
    answer = _answer(web_citations=[_web("http://www.Example.com/report/?sid=1#top")])

    NewsGrounder().validate(answer, set(), {SOURCE})

    assert len(answer.web_citations) == 1


def test_a_script_url_matching_a_source_after_comparison_is_removed() -> None:
    answer = _answer(
        citations=[_item()],
        web_citations=[_web("javascript://example.com/report?%0aalert(1)")],
    )

    NewsGrounder().validate(answer, {ITEM}, {SOURCE})

    assert answer.web_citations == []


def test_without_web_urls_every_web_citation_is_removed() -> None:
    answer = _answer(citations=[_item()], web_citations=[_web()])

    NewsGrounder().validate(answer, {ITEM})

    assert answer.web_citations == []


def test_an_unknown_item_citation_is_still_rejected_next_to_a_good_web_one() -> None:
    answer = _answer(citations=[_item()], web_citations=[_web()])

    with pytest.raises(GroundingError) as caught:
        NewsGrounder().validate(answer, set(), {SOURCE})

    assert caught.value.code == UNKNOWN_CHUNK


def test_an_answer_with_no_citations_at_all_is_still_rejected() -> None:
    with pytest.raises(GroundingError) as caught:
        NewsGrounder().validate(_answer(), set(), {SOURCE})

    assert caught.value.code == MISSING_CITATIONS


def test_an_index_shared_by_an_item_and_a_web_citation_is_rejected() -> None:
    answer = _answer(citations=[_item(1)], web_citations=[_web(index=1)])

    with pytest.raises(GroundingError) as caught:
        NewsGrounder().validate(answer, {ITEM}, {SOURCE})

    assert caught.value.code == DUPLICATE_INDEX


def test_a_removed_citation_cannot_cause_a_duplicate() -> None:
    answer = _answer(
        citations=[_item(1)], web_citations=[_web("https://made.up/page", index=1)]
    )

    NewsGrounder().validate(answer, {ITEM}, {SOURCE})

    assert answer.web_citations == []


def test_insufficient_evidence_with_a_web_citation_is_rejected() -> None:
    answer = _answer(web_citations=[_web()], insufficient_evidence=True)

    with pytest.raises(GroundingError) as caught:
        NewsGrounder().validate(answer, set(), {SOURCE})

    assert caught.value.code == INSUFFICIENT_WITH_CITATIONS

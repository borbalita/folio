import pytest

from evals.news_scoring import passes, pooled, score_extraction
from ingest.email.news import ExtractedItem

BODY = "A https://a.example/1 B https://b.example/2 C https://c.example/3 Ad https://ad.example/x"


def _item(title: str, url: str, sponsor: bool = False) -> ExtractedItem:
    return ExtractedItem(title=title, blurb="", url=url, sponsor=sponsor)


EXPECTED = [
    _item("Story A", "https://a.example/1"),
    _item("Story B", "https://b.example/2"),
    _item("Ad", "https://ad.example/x", sponsor=True),
    _item("Story C", "https://c.example/3"),
]


def test_a_perfect_run_scores_full_marks() -> None:
    scores = score_extraction(EXPECTED, list(EXPECTED), BODY)

    assert (scores.recall, scores.precision, scores.url_exact, scores.order) == (1, 1, 1, 1)
    assert (scores.sponsor_leaks, scores.sponsor_drops, scores.invented_urls) == (0, 0, 0)


def test_misses_leaks_drops_and_invented_urls_are_told_apart() -> None:
    actual = [
        _item("Story A", "https://a.example/1"),
        _item("Story B", "https://b.example/2", sponsor=True),  # news flagged as sponsor
        _item("Ad", "https://ad.example/x"),  # sponsor passed off as news
        _item("Extra", "https://made-up.example/story"),  # not expected, invented URL
    ]  # Story C missing

    scores = score_extraction(EXPECTED, actual, BODY)

    assert scores.expected_news == 3
    assert scores.returned_news == 3
    assert scores.found_news == 1
    assert scores.recall == pytest.approx(1 / 3)
    assert scores.precision == pytest.approx(1 / 3)
    assert scores.sponsor_leaks == 1
    assert scores.sponsor_drops == 1
    assert scores.invented_urls == 1


def test_wrong_url_on_a_found_item_and_swapped_order() -> None:
    actual = [
        _item("Story C", "https://c.example/3"),
        _item("Story A", "https://a.example/1?utm_source=x"),
        _item("Story B", "https://b.example/2"),
    ]

    scores = score_extraction(EXPECTED, actual, BODY)

    assert scores.recall == 1
    # The tracking parameter still matches the item but isn't the exact link.
    assert scores.url_exact == pytest.approx(2 / 3)
    # Pairs (A,B) in order; (A,C) and (B,C) reversed.
    assert scores.order == pytest.approx(1 / 3)


def test_an_empty_expected_url_is_matched_by_title_and_must_stay_empty() -> None:
    expected = [_item("Alpha story", "")]
    homepage = score_extraction(expected, [_item("Alpha story", "https://app.alphasignal.ai")], "")
    empty = score_extraction(expected, [_item("Alpha story", "")], "")

    assert homepage.recall == 1 and homepage.url_exact == 0 and homepage.invented_urls == 1
    assert empty.url_exact == 1 and empty.invented_urls == 0


def test_pooled_totals_and_the_pass_bar() -> None:
    good = score_extraction(EXPECTED, list(EXPECTED), BODY)
    leaky = score_extraction(EXPECTED, [*EXPECTED[:2], _item("Ad", "https://ad.example/x"), EXPECTED[3]], BODY)

    assert passes(pooled([good, good])) == (True, [])
    ok, reasons = passes(pooled([good, leaky]))
    assert not ok
    assert reasons == ["sponsor_leaks 1 > 0"]
    assert pooled([good, leaky])["recall"] == 1

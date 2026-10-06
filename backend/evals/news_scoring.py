"""Score one newsletter's extracted items against its expected items (plan 003).

Items are matched by normalized URL, then title similarity (evals.news_compare). Sponsors
are part of both lists, so a sponsor returned as news and news flagged as a sponsor can be
told apart from plain misses.
"""

from __future__ import annotations

from itertools import combinations

from pydantic import BaseModel

from evals.news_compare import match_items, url_in_text
from ingest.email.news import ExtractedItem


class ExtractionScores(BaseModel):
    expected_news: int
    returned_news: int
    found_news: int
    """Expected news items the run returned as news."""
    recall: float | None
    """found / expected news; None when the newsletter has no news items."""
    precision: float | None
    """found / returned news; None when the run returned no news."""
    exact_urls: int
    """Found news whose URL equals the expected one (empty included)."""
    url_exact: float | None
    """exact_urls / found news."""
    order: float | None
    """Share of found item pairs in the expected order; None with fewer than two."""
    sponsor_leaks: int
    """Expected sponsors returned as news."""
    sponsor_drops: int
    """Expected news returned flagged as a sponsor."""
    invented_urls: int
    """Returned news URLs that aren't usable article links in the newsletter text."""


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def score_extraction(
    expected: list[ExtractedItem], actual: list[ExtractedItem], body: str
) -> ExtractionScores:
    pairs = match_items(expected, actual)
    found = [
        (e, a) for e, a in pairs if not expected[e].sponsor and not actual[a].sponsor
    ]
    expected_news = sum(not item.sponsor for item in expected)
    returned = [item for item in actual if not item.sponsor]

    exact_urls = sum(expected[e].url.strip() == actual[a].url.strip() for e, a in found)
    in_order = [
        left_actual < right_actual
        for (_, left_actual), (_, right_actual) in combinations(sorted(found), 2)
    ]
    return ExtractionScores(
        expected_news=expected_news,
        returned_news=len(returned),
        found_news=len(found),
        recall=_ratio(len(found), expected_news),
        precision=_ratio(len(found), len(returned)),
        exact_urls=exact_urls,
        url_exact=_ratio(exact_urls, len(found)),
        order=_ratio(sum(in_order), len(in_order)),
        sponsor_leaks=sum(
            expected[e].sponsor and not actual[a].sponsor for e, a in pairs
        ),
        sponsor_drops=sum(
            not expected[e].sponsor and actual[a].sponsor for e, a in pairs
        ),
        invented_urls=sum(
            bool(item.url.strip()) and not url_in_text(item.url, body) for item in returned
        ),
    )


def pooled(scores: list[ExtractionScores]) -> dict[str, float | int | None]:
    """Totals over all newsletters; ratios pool the counts so long editions weigh more."""
    found = sum(s.found_news for s in scores)
    return {
        "expected_news": sum(s.expected_news for s in scores),
        "returned_news": sum(s.returned_news for s in scores),
        "found_news": found,
        "recall": _ratio(found, sum(s.expected_news for s in scores)),
        "precision": _ratio(found, sum(s.returned_news for s in scores)),
        "url_exact": _ratio(sum(s.exact_urls for s in scores), found),
        "order": _mean(s.order for s in scores),
        "sponsor_leaks": sum(s.sponsor_leaks for s in scores),
        "sponsor_drops": sum(s.sponsor_drops for s in scores),
        "invented_urls": sum(s.invented_urls for s in scores),
    }


def _mean(values: object) -> float | None:
    present = [value for value in values if value is not None]  # type: ignore[attr-defined]
    return sum(present) / len(present) if present else None


PASS_BAR = {"recall": 0.97, "url_exact": 0.98}


def passes(totals: dict[str, float | int | None]) -> tuple[bool, list[str]]:
    """The plan's bar; returns whether it passes and why not."""
    reasons: list[str] = []
    for metric, minimum in PASS_BAR.items():
        value = totals[metric]
        if value is None or value < minimum:
            shown = "None" if value is None else f"{value:.4f}"
            reasons.append(f"{metric} {shown} < {minimum}")
    for metric in ("sponsor_leaks", "invented_urls"):
        if totals[metric]:
            reasons.append(f"{metric} {totals[metric]} > 0")
    return not reasons, reasons

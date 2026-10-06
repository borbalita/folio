from evals.modes import extraction
from evals.news_runs import NewsletterResult
from ingest.email.news import ExtractedItem

PAYLOAD = {
    "input": {
        "key": "n01",
        "source": "tldr",
        "sent_date": "2026-09-01",
        "subject": "AI news",
        "body": "Story https://a.example/story",
    },
    "expected_output": {
        "items": [
            {"title": "Story", "url": "https://a.example/story", "sponsor": False},
            {"title": "Ad", "url": "", "sponsor": True},
        ]
    },
    "metadata": {"key": "n01", "review": "reference", "email_id": "e1"},
}


def _extracted(items: list[ExtractedItem] | None, error: str | None = None) -> NewsletterResult:
    return NewsletterResult(
        key="n01", items=items, error=error, input_tokens=1000, output_tokens=200, seconds=2.0
    )


def test_a_correct_extraction_scores_and_prices_the_newsletter() -> None:
    items = [
        ExtractedItem(title="Story", blurb="b", url="https://a.example/story"),
        ExtractedItem(title="Ad", blurb="b", url="", sponsor=True),
    ]

    result = extraction.evaluate(PAYLOAD, _extracted(items), "gpt-5.4-nano")

    assert result.scores is not None
    assert (result.scores.recall, result.scores.url_exact, result.scores.sponsor_leaks) == (1, 1, 0)
    assert result.cost_usd == (1000 * 0.20 + 200 * 1.25) / 1_000_000
    names = {evaluation.name for evaluation in extraction.extraction_evaluations(result)}
    assert {"recall", "url_exact", "sponsor_leaks", "invented_urls", "cost_usd", "seconds"} <= names


def test_a_failed_call_is_a_failure_not_a_zero_score() -> None:
    result = extraction.evaluate(PAYLOAD, _extracted(None, "APIConnectionError: boom"), "gpt-5.4-nano")

    assert result.scores is None
    (evaluation,) = extraction.extraction_evaluations(result)
    assert evaluation.name == "failed"

    summary = extraction.summarize([result])
    assert summary["failed"] == 1
    assert summary["passes_bar"] is False
    assert summary["bar_failures"] == [
        "recall None < 0.97",
        "url_exact None < 0.98",
        "1 newsletters failed",
    ]


def test_summary_passes_only_when_the_bar_holds() -> None:
    good = extraction.evaluate(
        PAYLOAD,
        _extracted([
            ExtractedItem(title="Story", blurb="", url="https://a.example/story"),
            ExtractedItem(title="Ad", blurb="", url="", sponsor=True),
        ]),
        "gpt-5.4-nano",
    )
    leak = extraction.evaluate(
        PAYLOAD,
        _extracted([
            ExtractedItem(title="Story", blurb="", url="https://a.example/story"),
            ExtractedItem(title="Ad", blurb="", url=""),
        ]),
        "gpt-5.4-nano",
    )

    assert extraction.summarize([good])["passes_bar"] is True
    leaky = extraction.summarize([good, leak])
    assert leaky["passes_bar"] is False
    assert leaky["bar_failures"] == ["sponsor_leaks 1 > 0"]

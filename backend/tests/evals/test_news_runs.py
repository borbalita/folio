from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError

from evals import news_runs
from evals.news_data import Newsletter
from ingest.email.news import ExtractedItem, Extraction

NEWSLETTER = Newsletter(
    key="n01",
    source="tldr",
    sent_date=date(2026, 9, 1),
    subject="AI news",
    body="Story one",
    email_id="00000000-0000-0000-0000-000000000001",
)


def _completion(items: list[ExtractedItem]) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=300,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=100),
    )
    message = SimpleNamespace(parsed=Extraction(items=items))
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)])


def test_extract_one_keeps_items_sponsors_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    items = [
        ExtractedItem(title="A", blurb="a", url="https://a.example"),
        ExtractedItem(title="Ad", blurb="buy", url="https://ad.example", sponsor=True),
    ]

    def request(parsed: object, *, model: str, reasoning_effort: object) -> object:
        calls.append({"subject": parsed.subject, "body": parsed.body, "model": model, "effort": reasoning_effort})
        return _completion(items)

    monkeypatch.setattr(news_runs, "request_extraction", request)

    result = news_runs.extract_one(NEWSLETTER, "cheap-model", "none")

    assert calls == [{"subject": "AI news", "body": "Story one", "model": "cheap-model", "effort": "none"}]
    assert result.items == items
    assert result.error is None
    assert (result.input_tokens, result.output_tokens, result.reasoning_tokens) == (1000, 300, 100)


def test_extract_one_records_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def request(*_args: object, **_kwargs: object) -> object:
        raise APIConnectionError(request=httpx.Request("POST", "https://api.example"))

    monkeypatch.setattr(news_runs, "request_extraction", request)

    result = news_runs.extract_one(NEWSLETTER, "cheap-model", None)

    assert result.items is None
    assert result.error is not None and result.error.startswith("APIConnectionError")


def test_summary_prices_known_models_and_counts_sponsors() -> None:
    run = news_runs.RunFile(
        version="news-test",
        model="gpt-5.4-nano",
        effort="none",
        started_at=datetime(2026, 10, 6, tzinfo=UTC),
        results=[
            news_runs.NewsletterResult(
                key="n01",
                items=[
                    ExtractedItem(title="A", blurb="a", url="https://a.example"),
                    ExtractedItem(title="Ad", blurb="b", url="https://ad.example", sponsor=True),
                ],
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
            news_runs.NewsletterResult(key="n02", items=None, error="boom"),
        ],
    )

    summary = news_runs.summarize(run)

    assert "gpt-5.4-nano@none: 1/2 ok" in summary
    assert "2 items (1 flagged sponsor)" in summary
    assert "$1.45" in summary

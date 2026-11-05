from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import structlog
from openai import APIConnectionError, LengthFinishReasonError

from app.notifications import store, summary
from app.notifications.detect import NewsItemFacts, StoryFacts
from app.notifications.summary import NewsSummary

ITEMS = [
    NewsItemFacts(id=uuid.uuid4(), email_id=uuid.uuid4(), position=0, source="tldr", title="Lab ships model X", blurb="It is fast.", url="https://tldr.test/x"),
    NewsItemFacts(id=uuid.uuid4(), email_id=uuid.uuid4(), position=3, source="alpha_signal", title="Model X is out", blurb="Beats Y on Z.", url="https://alpha.test/x"),
]


EDITIONS = {
    ITEMS[0].email_id: "TLDR whole newsletter: Lab ships model X. Much more text. Unrelated story Q.",
    ITEMS[1].email_id: "Alpha whole newsletter: Model X is out, explained at length.",
}


def _completion(parsed: NewsSummary | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


def test_summary_text_has_headline_summary_and_both_links(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def ask(items, editions):
        calls.append((items, editions))
        return _completion(NewsSummary(headline="Model X launches", summary="Fast, and beats Y on Z."))

    monkeypatch.setattr(summary, "request_summary", ask)

    text = summary.news_text(ITEMS, EDITIONS)

    assert text == (
        "📰 Model X launches\nFast, and beats Y on Z.\n"
        "TLDR: https://tldr.test/x · Alpha Signal: https://alpha.test/x"
    )
    assert calls == [(ITEMS, EDITIONS)]


def test_model_error_falls_back_to_the_first_headline_and_blurb(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(items, editions):
        raise APIConnectionError(request=MagicMock())

    monkeypatch.setattr(summary, "request_summary", fail)

    with structlog.testing.capture_logs() as logs:
        text = summary.news_text(ITEMS, EDITIONS)

    assert text.startswith("📰 Lab ships model X\nIt is fast.\n")
    assert {"event": "news_summary_failed", "error": "APIConnectionError", "log_level": "warning"} in logs


@pytest.mark.parametrize(
    "error",
    [
        LengthFinishReasonError(completion=MagicMock()),
        ValueError("model returned something unparseable"),
    ],
)
def test_any_model_error_falls_back(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fail(items, editions):
        raise error

    monkeypatch.setattr(summary, "request_summary", fail)

    with structlog.testing.capture_logs() as logs:
        text = summary.news_text(ITEMS, EDITIONS)

    assert text.startswith("📰 Lab ships model X\n")
    assert [e["error"] for e in logs if e["event"] == "news_summary_failed"] == [type(error).__name__]


def test_the_prompt_has_each_whole_newsletter_and_names_the_titles() -> None:
    messages = summary.summary_messages(ITEMS, EDITIONS)

    user = messages[-1]["content"]
    assert "Lab ships model X" in user and "Model X is out" in user
    for body in EDITIONS.values():
        assert body in user
    assert "https://" not in user


def test_two_items_in_one_newsletter_include_that_edition_once() -> None:
    same = [ITEMS[0], replace(ITEMS[1], email_id=ITEMS[0].email_id)]

    user = summary.summary_messages(same, EDITIONS)[-1]["content"]

    assert user.count(EDITIONS[ITEMS[0].email_id]) == 1
    assert "Model X is out" in user


def test_the_prompt_limits_facts_to_the_newsletters() -> None:
    system = summary.summary_messages(ITEMS, EDITIONS)[0]["content"]

    assert "only from the newsletters" in system
    assert "why it matters" in system


def test_failed_call_keeps_the_blurb_when_there_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(items, editions):
        raise APIConnectionError(request=MagicMock())

    monkeypatch.setattr(summary, "request_summary", fail)

    assert summary.news_text(ITEMS, EDITIONS) == (
        "📰 Lab ships model X\nIt is fast.\n"
        "TLDR: https://tldr.test/x · Alpha Signal: https://alpha.test/x"
    )


def test_failed_call_with_an_empty_blurb_has_no_empty_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(items, editions):
        raise ValueError("unparseable")

    monkeypatch.setattr(summary, "request_summary", fail)
    items = [replace(ITEMS[0], blurb="")]

    text = summary.news_text(items, EDITIONS)

    assert text == "📰 Lab ships model X\nTLDR: https://tldr.test/x"
    assert "\n\n" not in text


def _record(monkeypatch, *, known: set[str], enabled: bool) -> list[str]:
    asked: list[str] = []
    monkeypatch.setattr(
        summary, "news_text", lambda items, editions: asked.append(editions) or "summary text"
    )
    monkeypatch.setattr(
        store, "load_editions", lambda session, email_ids: {i: f"body {i}" for i in email_ids}
    )
    monkeypatch.setattr(store, "load_invoices", lambda session: [])
    monkeypatch.setattr(store, "load_big_stories", lambda session, since: [StoryFacts(items=ITEMS)])
    monkeypatch.setattr(store, "known_keys", lambda session: set(known))
    monkeypatch.setattr(store, "telegram_enabled", lambda: enabled)
    inserted: list = []
    monkeypatch.setattr(store, "insert_rows", lambda session, rows: inserted.extend(rows))
    store.record_notifications(MagicMock(), datetime(2026, 10, 19, 12, tzinfo=UTC))
    return asked, inserted


def test_new_big_story_is_summarised_once(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, inserted = _record(monkeypatch, known=set(), enabled=True)

    assert asked == [{i.email_id: f"body {i.email_id}" for i in ITEMS}]
    [pending] = [row for row in inserted if row.status == "pending"]
    assert pending.text == "summary text"


def test_already_announced_story_never_calls_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, _ = _record(
        monkeypatch,
        known={f"news:{i.email_id}:{i.position}" for i in ITEMS},
        enabled=True,
    )

    assert asked == []


def test_disabled_telegram_never_calls_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, inserted = _record(monkeypatch, known=set(), enabled=False)

    assert asked == []
    assert all(row.status == "skipped" for row in inserted)



def test_summary_without_any_links_has_no_link_line(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [ITEMS[0].__class__(**{**ITEMS[1].__dict__, "url": ""})]
    monkeypatch.setattr(
        summary, "request_summary",
        lambda items, editions: _completion(NewsSummary(headline="H", summary="S.")),
    )

    assert summary.news_text(items, EDITIONS) == "📰 H\nS."

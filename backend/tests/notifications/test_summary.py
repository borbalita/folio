from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import structlog
from openai import APIConnectionError

from app.notifications import store, summary
from app.notifications.detect import NewsItemFacts, StoryFacts
from app.notifications.summary import NewsSummary

ITEMS = [
    NewsItemFacts(id=uuid.uuid4(), source="tldr", title="Lab ships model X", blurb="It is fast.", url="https://tldr.test/x"),
    NewsItemFacts(id=uuid.uuid4(), source="alpha_signal", title="Model X is out", blurb="Beats Y on Z.", url="https://alpha.test/x"),
]


def _completion(parsed: NewsSummary | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


def test_summary_text_has_headline_summary_and_both_links(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def ask(items):
        calls.append(items)
        return _completion(NewsSummary(headline="Model X launches", summary="Fast, and beats Y on Z."))

    monkeypatch.setattr(summary, "request_summary", ask)

    text = summary.news_text(ITEMS)

    assert text == (
        "📰 Model X launches\nFast, and beats Y on Z.\n"
        "TLDR: https://tldr.test/x · Alpha Signal: https://alpha.test/x"
    )
    assert calls == [ITEMS]


def test_model_error_falls_back_to_the_first_title(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(items):
        raise APIConnectionError(request=MagicMock())

    monkeypatch.setattr(summary, "request_summary", fail)

    with structlog.testing.capture_logs() as logs:
        text = summary.news_text(ITEMS)

    assert text == "📰 Lab ships model X\nTLDR: https://tldr.test/x · Alpha Signal: https://alpha.test/x"
    assert {"event": "news_summary_failed", "error": "APIConnectionError", "log_level": "warning"} in logs


def test_the_prompt_sees_only_titles_and_blurbs() -> None:
    messages = summary.summary_messages(ITEMS)

    user = messages[-1]["content"]
    assert "Lab ships model X" in user and "Beats Y on Z." in user
    assert "https://" not in user


def _record(monkeypatch, *, known: set[str], enabled: bool) -> list[str]:
    asked: list[str] = []
    monkeypatch.setattr(summary, "news_text", lambda items: asked.append("asked") or "summary text")
    monkeypatch.setattr(store, "load_invoices", lambda session: [])
    monkeypatch.setattr(store, "load_big_stories", lambda session: [StoryFacts(items=ITEMS)])
    monkeypatch.setattr(store, "known_keys", lambda session: set(known))
    monkeypatch.setattr(store, "telegram_enabled", lambda: enabled)
    inserted: list = []
    monkeypatch.setattr(store, "insert_rows", lambda session, rows: inserted.extend(rows))
    store.record_notifications(MagicMock(), datetime(2026, 10, 19, 12, tzinfo=UTC))
    return asked, inserted


def test_new_big_story_is_summarised_once(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, inserted = _record(monkeypatch, known=set(), enabled=True)

    assert asked == ["asked"]
    [pending] = [row for row in inserted if row.status == "pending"]
    assert pending.text == "summary text"


def test_already_announced_story_never_calls_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, _ = _record(monkeypatch, known={f"news:{ITEMS[0].id}", f"news:{ITEMS[1].id}"}, enabled=True)

    assert asked == []


def test_disabled_telegram_never_calls_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, inserted = _record(monkeypatch, known=set(), enabled=False)

    assert asked == []
    assert all(row.status == "skipped" for row in inserted)

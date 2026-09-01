from __future__ import annotations

from unittest.mock import MagicMock

from openai import APIError

from app.chat.titles import (
    DEFAULT_THREAD_TITLE,
    TITLE_MAX_CHARS,
    ThreadTitle,
    generate_thread_title,
    title_from_question,
)


def _patch_parse(monkeypatch, parsed: object) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.parsed = parsed
    client = MagicMock()
    client.chat.completions.parse.return_value = completion
    monkeypatch.setattr("app.chat.titles._client", lambda: client)
    return client


def test_title_from_question_collapses_and_truncates() -> None:
    long = "word " * 40
    title = title_from_question(f"  {long}  ")
    assert "\n" not in title
    assert len(title) <= TITLE_MAX_CHARS
    assert title.endswith("…")


def test_title_from_question_empty_is_default() -> None:
    assert title_from_question("   ") == DEFAULT_THREAD_TITLE


def test_generate_thread_title_uses_parsed_title(monkeypatch) -> None:
    _patch_parse(monkeypatch, ThreadTitle(title="AAPL Services FY2023"))
    assert generate_thread_title(
        "How did Services do?", "Services revenue increased."
    ) == ("AAPL Services FY2023")


def test_generate_thread_title_strips_quotes(monkeypatch) -> None:
    _patch_parse(monkeypatch, ThreadTitle(title='"AAPL Services"'))
    assert generate_thread_title("How did Services do?", "up") == "AAPL Services"


def test_generate_thread_title_falls_back_when_unparsed(monkeypatch) -> None:
    _patch_parse(monkeypatch, None)
    assert generate_thread_title("How did Services do?", "up") == "How did Services do?"


def test_generate_thread_title_falls_back_on_api_error(monkeypatch) -> None:
    client = MagicMock()
    client.chat.completions.parse.side_effect = APIError(
        "quota",
        request=MagicMock(),
        body=None,
    )
    monkeypatch.setattr("app.chat.titles._client", lambda: client)
    assert generate_thread_title("How did Services do?", "up") == "How did Services do?"

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.retrieval.keywords import FtsKeywords, extract_fts_keywords


def _patch_parse(monkeypatch, parsed: object) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.parsed = parsed
    client = MagicMock()
    client.chat.completions.parse.return_value = completion
    monkeypatch.setattr("app.retrieval.keywords._client", lambda: client)
    return client


def test_extract_fts_keywords_joins_terms(monkeypatch) -> None:
    _patch_parse(monkeypatch, FtsKeywords(keywords=["Apple", "iPhone", "Services"]))
    assert (
        extract_fts_keywords("How did Apple's iPhone Services mix change?")
        == "Apple iPhone Services"
    )


def test_extract_fts_keywords_falls_back_when_unparsed(monkeypatch) -> None:
    query = "How did they do it?"
    _patch_parse(monkeypatch, None)
    assert extract_fts_keywords(query) == query


def test_extract_fts_keywords_falls_back_when_empty(monkeypatch) -> None:
    query = "How did they do it?"
    _patch_parse(monkeypatch, SimpleNamespace(keywords=[]))
    assert extract_fts_keywords(query) == query

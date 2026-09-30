from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.retrieval.keywords import FtsKeywords, extract_fts_keywords

PROMPT = "Extract keywords."


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
        extract_fts_keywords(
            "How did Apple's iPhone Services mix change?", system_prompt=PROMPT
        )
        == "Apple iPhone Services"
    )


def test_extract_fts_keywords_sends_the_system_prompt(monkeypatch) -> None:
    client = _patch_parse(monkeypatch, FtsKeywords(keywords=["Telekom"]))

    extract_fts_keywords("Telekom bill?", system_prompt=PROMPT)

    messages = client.chat.completions.parse.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": PROMPT}


def test_extract_fts_keywords_accepts_a_single_keyword(monkeypatch) -> None:
    _patch_parse(monkeypatch, FtsKeywords(keywords=["Telekom"]))
    assert extract_fts_keywords("Telekom bill?", system_prompt=PROMPT) == "Telekom"


def test_extract_fts_keywords_falls_back_when_unparsed(monkeypatch) -> None:
    query = "How did they do it?"
    _patch_parse(monkeypatch, None)
    assert extract_fts_keywords(query, system_prompt=PROMPT) == query


def test_extract_fts_keywords_falls_back_when_empty(monkeypatch) -> None:
    query = "How did they do it?"
    _patch_parse(monkeypatch, SimpleNamespace(keywords=[]))
    assert extract_fts_keywords(query, system_prompt=PROMPT) == query

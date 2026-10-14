from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.retrieval.news.queries import NewsSearchFilters
from app.retrieval.news.retriever import NewsPassage, NewsRetriever
from app.retrieval.queries import RankedHit
from tests.conftest import span_text

USER = UUID("00000000-0000-0000-0000-000000000001")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
A = UUID("00000000-0000-0000-0000-0000000000a1")
B = UUID("00000000-0000-0000-0000-0000000000a2")
C = UUID("00000000-0000-0000-0000-0000000000a3")
STORY_1 = UUID("00000000-0000-0000-0000-0000000000c1")
STORY_2 = UUID("00000000-0000-0000-0000-0000000000c2")


def _filters(**overrides: object) -> NewsSearchFilters:
    values: dict[str, object] = {"user_id": USER, "mailbox_ids": [OWNED]}
    values.update(overrides)
    return NewsSearchFilters.model_validate(values)


def _passage(item_id: UUID) -> NewsPassage:
    return NewsPassage(
        item_id=item_id,
        story_id=None,
        source="tldr",
        edition_date=date(2026, 9, 22),
        title=f"Item {item_id}",
        blurb="Blurb",
        url="https://example.com",
        score=0.0,
    )


def _row(
    item_id: UUID, story_id: UUID, source: str, last_seen: date
) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id,
        story_id=story_id,
        source=source,
        edition_date=last_seen,
        title="Title",
        blurb="Blurb",
        url="https://example.com",
        first_seen=date(2026, 9, 20),
        last_seen=last_seen,
    )


class _Session:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.sql = ""
        self.params: dict[str, object] = {}

    def execute(self, statement: object, params: dict[str, object]) -> SimpleNamespace:
        self.sql = str(statement)
        self.params = params
        return SimpleNamespace(all=lambda: self.rows)


def test_search_with_no_mailbox_does_not_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_query: str) -> list[float]:
        raise AssertionError("embed should not run")

    monkeypatch.setattr("app.retrieval.news.retriever.embed_query", fail)

    found = NewsRetriever().search(
        "robots", filters=_filters(mailbox_ids=[]), session=object()
    )

    assert found == []


def test_search_keeps_rank_order_and_drops_items_outside_the_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.retrieval.news.retriever.embed_query", lambda _q: [0.1])
    monkeypatch.setattr(
        "app.retrieval.news.queries.NewsQueries.semantic",
        lambda *_args, **_kwargs: [
            RankedHit(chunk_id=B, rank=1, score=0.9),
            RankedHit(chunk_id=C, rank=2, score=0.8),
            RankedHit(chunk_id=A, rank=3, score=0.7),
        ],
    )
    monkeypatch.setattr(
        "app.retrieval.news.retriever.load_news_items",
        lambda _session, _ids, _filters: {A: _passage(A), B: _passage(B)},
    )

    found = NewsRetriever().search("robots", filters=_filters(), session=object())

    assert [passage.item_id for passage in found] == [B, A]
    assert [passage.score for passage in found] == [0.9, 0.7]


def test_big_stories_groups_rows_by_story_in_order() -> None:
    session = _Session(
        [
            _row(A, STORY_1, "alpha_signal", date(2026, 9, 22)),
            _row(B, STORY_1, "tldr", date(2026, 9, 22)),
            _row(C, STORY_2, "tldr", date(2026, 9, 21)),
        ]
    )

    stories = NewsRetriever().big_stories(
        filters=_filters(since="2026-09-15", until="2026-09-22"),
        session=session,  # type: ignore[arg-type]
    )

    assert [story.story_id for story in stories] == [STORY_1, STORY_2]
    assert [item.item_id for item in stories[0].items] == [A, B]
    assert stories[0].last_seen == date(2026, 9, 22)
    assert "s.is_big IS TRUE" in session.sql
    assert "s.first_seen <= :until" in session.sql
    assert "s.last_seen >= :since" in session.sql
    assert "m.user_id = :user_id" in session.sql
    assert session.params["since"] == date(2026, 9, 15)


def test_big_stories_without_dates_has_no_range_condition() -> None:
    session = _Session([])

    stories = NewsRetriever().big_stories(filters=_filters(), session=session)  # type: ignore[arg-type]

    assert stories == []
    assert ":until" not in session.sql
    assert ":since" not in session.sql


def test_big_stories_with_no_mailbox_runs_no_query() -> None:
    session = _Session([])

    assert (
        NewsRetriever().big_stories(filters=_filters(mailbox_ids=[]), session=session)  # type: ignore[arg-type]
        == []
    )
    assert session.sql == ""


def test_search_span_has_settings_not_query_or_filters(
    monkeypatch: pytest.MonkeyPatch, langfuse_spans: Callable[[], tuple]
) -> None:
    monkeypatch.setattr("app.retrieval.news.retriever.embed_query", lambda _q: [0.1])
    monkeypatch.setattr(
        "app.retrieval.news.queries.NewsQueries.semantic",
        lambda *_args, **_kwargs: [RankedHit(chunk_id=A, rank=1, score=0.9)],
    )
    monkeypatch.setattr(
        "app.retrieval.news.retriever.load_news_items",
        lambda _session, _ids, _filters: {A: _passage(A)},
    )

    NewsRetriever().search(
        "SECRET-Q", filters=_filters(since=date(2026, 9, 17)), session=object()
    )

    spans = langfuse_spans()
    search = span_text(spans, "news-search")
    assert "SECRET" not in search
    assert "2026-09-17" not in search
    assert "'langfuse.observation.metadata.passage_count': 1" in search
    assert "SECRET" not in span_text(spans, "embed-query")

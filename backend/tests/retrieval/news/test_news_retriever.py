from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.retrieval.news.queries import NewsSearchFilters
from app.retrieval.news.retriever import NewsPassage, NewsRetriever, Story, rank_stories
from app.retrieval.queries import RankedHit
from tests.conftest import span_text

USER = UUID("00000000-0000-0000-0000-000000000001")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
A = UUID("00000000-0000-0000-0000-0000000000a1")
B = UUID("00000000-0000-0000-0000-0000000000a2")
C = UUID("00000000-0000-0000-0000-0000000000a3")
STORY_1 = UUID("00000000-0000-0000-0000-0000000000c1")
STORY_2 = UUID("00000000-0000-0000-0000-0000000000c2")
STORY_3 = UUID("00000000-0000-0000-0000-0000000000c3")
STORY_4 = UUID("00000000-0000-0000-0000-0000000000c4")
STORY_5 = UUID("00000000-0000-0000-0000-0000000000c5")


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


def _story(
    story_id: UUID,
    *,
    is_big: bool = False,
    sources: tuple[str, ...] = ("tldr",),
    items: int = 1,
    first: str = "2026-10-12",
    last: str = "2026-10-12",
) -> Story:
    return Story(
        story_id=story_id,
        first_seen=date.fromisoformat(first),
        last_seen=date.fromisoformat(last),
        is_big=is_big,
        sources=list(sources),
        item_count=items,
        items=[],
    )


def test_rank_puts_big_first_then_sources_items_days_newest() -> None:
    big = _story(STORY_1, is_big=True, sources=("alpha_signal", "tldr"), items=2)
    many_items = _story(STORY_2, items=4)
    long_run = _story(STORY_3, first="2026-10-10", last="2026-10-13")
    newer = _story(STORY_4, first="2026-10-14", last="2026-10-14")
    older = _story(STORY_5, first="2026-10-11", last="2026-10-11")

    ranked = rank_stories([older, newer, long_run, many_items, big])

    assert ranked == [big, many_items, long_run, newer, older]


def test_rank_breaks_full_ties_by_story_id() -> None:
    first, second = _story(STORY_1), _story(STORY_2)

    assert rank_stories([second, first]) == [first, second]
    assert rank_stories([first, second]) == [first, second]


def _aggregate(
    story_id: UUID,
    *,
    is_big: bool = False,
    sources: tuple[str, ...] = ("tldr",),
    items: int = 1,
    first: date = date(2026, 10, 12),
    last: date = date(2026, 10, 12),
) -> SimpleNamespace:
    return SimpleNamespace(
        id=story_id,
        first_seen=first,
        last_seen=last,
        is_big=is_big,
        sources=list(sources),
        item_count=items,
    )


class _Queries:
    """Answers each execute() with the next result set and records statements."""

    def __init__(self, *results: list[SimpleNamespace]) -> None:
        self.results = list(results)
        self.statements: list[str] = []
        self.params: list[dict[str, object]] = []

    def execute(self, statement: object, params: dict[str, object]) -> SimpleNamespace:
        self.statements.append(str(statement))
        self.params.append(params)
        rows = self.results.pop(0)
        return SimpleNamespace(all=lambda: rows)


def test_stories_keeps_the_top_ranked_not_the_newest() -> None:
    newest_single = _aggregate(
        STORY_1, last=date(2026, 10, 18), first=date(2026, 10, 18)
    )
    older_big = _aggregate(
        STORY_2, is_big=True, sources=("alpha_signal", "tldr"), items=2
    )
    two_items = _aggregate(
        STORY_3, items=2, first=date(2026, 10, 14), last=date(2026, 10, 14)
    )
    session = _Queries(
        [newest_single, older_big, two_items],
        [
            _row(B, STORY_3, "tldr", date(2026, 10, 14)),
            _row(A, STORY_2, "alpha_signal", date(2026, 10, 12)),
            _row(C, STORY_2, "tldr", date(2026, 10, 12)),
        ],
    )

    stories = NewsRetriever().stories(filters=_filters(), limit=2, session=session)  # type: ignore[arg-type]

    assert [story.story_id for story in stories] == [STORY_2, STORY_3]
    assert [item.item_id for item in stories[0].items] == [A, C]
    assert [item.item_id for item in stories[1].items] == [B]
    assert stories[0].sources == ["alpha_signal", "tldr"]
    assert stories[0].item_count == 2
    assert session.params[1]["story_ids"] == [STORY_2, STORY_3]


def test_stories_big_only_and_dates_go_into_the_aggregate_query() -> None:
    session = _Queries([])

    stories = NewsRetriever().stories(
        filters=_filters(big_only=True, since="2026-10-12", until="2026-10-18"),
        limit=10,
        session=session,  # type: ignore[arg-type]
    )

    assert stories == []
    sql, params = session.statements[0], session.params[0]
    assert "count(DISTINCT ni.source) > 1" in sql
    assert "max(ni.edition_date) >= :since" in sql
    assert "min(ni.edition_date) <= :until" in sql
    assert params["since"] == date(2026, 10, 12)
    assert params["until"] == date(2026, 10, 18)
    assert len(session.statements) == 1


def test_stories_without_dates_or_big_only_has_no_such_conditions() -> None:
    session = _Queries([])

    NewsRetriever().stories(filters=_filters(), limit=10, session=session)  # type: ignore[arg-type]

    sql = session.statements[0]
    assert ":since" not in sql
    assert ":until" not in sql
    assert "HAVING" not in sql


def test_stories_scope_both_queries_to_the_user() -> None:
    session = _Queries(
        [_aggregate(STORY_1)], [_row(A, STORY_1, "tldr", date(2026, 10, 12))]
    )

    NewsRetriever().stories(filters=_filters(), limit=10, session=session)  # type: ignore[arg-type]

    for sql, params in zip(session.statements, session.params, strict=True):
        assert "m.user_id = :user_id" in sql
        assert params["user_id"] == USER


def test_stories_with_no_mailbox_runs_no_query() -> None:
    session = _Queries()

    stories = NewsRetriever().stories(
        filters=_filters(mailbox_ids=[]),
        limit=10,
        session=session,  # type: ignore[arg-type]
    )

    assert stories == []
    assert session.statements == []


def test_story_days_counts_first_and_last_day() -> None:
    assert _story(STORY_1, first="2026-10-12", last="2026-10-14").days == 3
    assert _story(STORY_1).days == 1


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


def test_big_and_dates_come_from_the_users_own_items_only() -> None:
    # The shared story row may be big or wider because of another mailbox's items.
    session = _Queries([])

    NewsRetriever().stories(filters=_filters(), limit=10, session=session)  # type: ignore[arg-type]

    sql = session.statements[0]
    assert "s.is_big" not in sql
    assert "s.first_seen" not in sql
    assert "s.last_seen" not in sql
    assert "min(ni.edition_date) AS first_seen" in sql
    assert "max(ni.edition_date) AS last_seen" in sql
    assert "count(DISTINCT ni.source) > 1 AS is_big" in sql

from __future__ import annotations

from uuid import UUID

from app.retrieval.news.queries import NewsQueries, NewsSearchFilters

USER = UUID("00000000-0000-0000-0000-000000000001")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
QUERIES = NewsQueries()


def _filters(**overrides: object) -> NewsSearchFilters:
    values: dict[str, object] = {"user_id": USER, "mailbox_ids": [OWNED]}
    values.update(overrides)
    return NewsSearchFilters.model_validate(values)


def test_sql_searches_news_items_scoped_to_the_user() -> None:
    sql = QUERIES.semantic_sql(_filters())
    assert "news_items ni" in sql
    assert "LEFT JOIN news_stories s ON s.id = ni.story_id" in sql
    assert "m.user_id = :user_id" in sql
    assert "m.id = ANY(:mailbox_ids)" in sql
    assert "m.is_active IS TRUE" in sql


def test_no_optional_filters_adds_only_the_scope() -> None:
    clause = QUERIES.filter_clause(_filters())
    assert "edition_date" not in clause.sql
    assert "is_big" not in clause.sql
    assert set(clause.params) == {"user_id", "mailbox_ids"}


def test_filters_narrow_edition_dates_and_big_stories() -> None:
    clause = QUERIES.filter_clause(
        _filters(since="2026-09-01", until="2026-09-28", big_only=True)
    )
    assert "ni.edition_date >= :since" in clause.sql
    assert "ni.edition_date <= :until" in clause.sql
    assert "s.is_big IS TRUE" in clause.sql

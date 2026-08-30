from __future__ import annotations

from app.retrieval.queries import (
    SearchFilters,
    build_full_text_search_sql,
    build_semantic_search_sql,
)


def test_semantic_sql_uses_cosine_distance() -> None:
    sql = build_semantic_search_sql()
    assert "<=>" in sql
    assert "CAST(:query_vec AS vector)" in sql
    assert "LIMIT :limit" in sql


def test_fts_sql_uses_plainto_tsquery_and_rank() -> None:
    sql = build_full_text_search_sql()
    assert "plainto_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "CAST(:fts_config AS regconfig)" in sql
    assert "search_vector @@ query" in sql


def test_filters_added_to_both_queries() -> None:
    filters = SearchFilters(ticker="AAPL", fiscal_years=[2023], form="10-K")
    semantic = build_semantic_search_sql(filters)
    fts = build_full_text_search_sql(filters)
    for sql in (semantic, fts):
        assert "sd.ticker = :ticker" in sql
        assert "sd.fiscal_year = ANY(:fiscal_years)" in sql
        assert "sd.filing_type = :form" in sql

from __future__ import annotations

from app.retrieval.documents.queries import DocumentQueries, DocumentSearchFilters

QUERIES = DocumentQueries()


def test_semantic_sql_uses_cosine_distance() -> None:
    sql = QUERIES.semantic_sql(DocumentSearchFilters())
    assert "<=>" in sql
    assert "CAST(:query_vec AS vector)" in sql
    assert "dc.embedding IS NOT NULL" in sql
    assert "LIMIT :limit" in sql


def test_fts_sql_uses_plainto_tsquery_and_rank() -> None:
    sql = QUERIES.full_text_sql(DocumentSearchFilters())
    assert "plainto_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "CAST(:fts_config AS regconfig)" in sql
    assert "dc.search_vector @@ query" in sql


def test_no_filters_adds_no_condition() -> None:
    sql = QUERIES.semantic_sql(DocumentSearchFilters())
    assert "sd.ticker" not in sql
    assert "AND" not in sql


def test_filters_added_to_both_queries() -> None:
    filters = DocumentSearchFilters(ticker="AAPL", fiscal_years=[2023], form="10-K")
    for sql in (QUERIES.semantic_sql(filters), QUERIES.full_text_sql(filters)):
        assert "sd.ticker = :ticker" in sql
        assert "sd.fiscal_year = ANY(:fiscal_years)" in sql
        assert "sd.filing_type = :form" in sql

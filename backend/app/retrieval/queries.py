"""pgvector semantic search and Postgres full-text search over document_chunks."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


class SearchFilters(BaseModel):
    ticker: str | None = None
    fiscal_years: list[int] | None = None
    form: str | None = None


class RankedChunkHit(BaseModel):
    chunk_id: UUID
    rank: int
    score: float | None = None


@dataclass(frozen=True, slots=True)
class _FilterClause:
    sql: str
    params: dict[str, object]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


def _build_filters(filters: SearchFilters | None) -> _FilterClause:
    if filters is None:
        return _FilterClause("", {})

    clauses: list[str] = []
    params: dict[str, object] = {}

    if filters.ticker is not None:
        clauses.append("sd.ticker = :ticker")
        params["ticker"] = filters.ticker
    if filters.fiscal_years:
        clauses.append("sd.fiscal_year = ANY(:fiscal_years)")
        params["fiscal_years"] = filters.fiscal_years
    if filters.form is not None:
        clauses.append("sd.filing_type = :form")
        params["form"] = filters.form

    if not clauses:
        return _FilterClause("", {})

    return _FilterClause(" AND " + " AND ".join(clauses), params)


def _rows_to_hits(rows: list) -> list[RankedChunkHit]:
    return [
        RankedChunkHit(
            chunk_id=UUID(str(row.id)),
            rank=index,
            score=float(row.score) if row.score is not None else None,
        )
        for index, row in enumerate(rows, start=1)
    ]


def _semantic_sql_template(filter_clause: _FilterClause) -> str:
    return f"""
        SELECT dc.id,
               1 - (dc.embedding <=> CAST(:query_vec AS vector)) AS score
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE dc.embedding IS NOT NULL
        {filter_clause.sql}
        ORDER BY dc.embedding <=> CAST(:query_vec AS vector)
        LIMIT :limit
    """


def _fts_sql_template(filter_clause: _FilterClause) -> str:
    return f"""
        SELECT dc.id,
               ts_rank_cd(dc.search_vector, query) AS score
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id,
             plainto_tsquery(CAST(:fts_config AS regconfig), :query_text) query
        WHERE dc.search_vector @@ query
        {filter_clause.sql}
        ORDER BY score DESC
        LIMIT :limit
    """


def build_semantic_search_sql(filters: SearchFilters | None = None) -> str:
    return _semantic_sql_template(_build_filters(filters))


def build_full_text_search_sql(filters: SearchFilters | None = None) -> str:
    return _fts_sql_template(_build_filters(filters))


def semantic_search(
    session: Session,
    query_vec: list[float],
    *,
    limit: int,
    filters: SearchFilters | None = None,
) -> list[RankedChunkHit]:
    filter_clause = _build_filters(filters)
    params: dict[str, object] = {
        "query_vec": _vector_literal(query_vec),
        "limit": limit,
        **filter_clause.params,
    }
    rows = session.execute(text(build_semantic_search_sql(filters)), params).all()
    return _rows_to_hits(rows)


def full_text_search(
    session: Session,
    query_text: str,
    *,
    limit: int,
    filters: SearchFilters | None = None,
) -> list[RankedChunkHit]:
    filter_clause = _build_filters(filters)
    params: dict[str, object] = {
        "fts_config": settings.retrieval_fts_config,
        "query_text": query_text,
        "limit": limit,
        **filter_clause.params,
    }
    rows = session.execute(text(build_full_text_search_sql(filters)), params).all()
    return _rows_to_hits(rows)

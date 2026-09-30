"""Semantic (pgvector) and full-text SQL over one chunk table. Subclasses name the table and filters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


class RankedHit(BaseModel):
    chunk_id: UUID
    rank: int
    score: float | None = None


@dataclass(frozen=True, slots=True)
class FilterClause:
    """SQL conditions joined with AND, plus their bind params. Empty sql means no filter."""

    sql: str
    params: dict[str, object]


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


class ChunkQueries[FiltersT: BaseModel](ABC):
    chunks: ClassVar[str]
    """Alias of the chunk table in `from_sql`, e.g. `dc`."""
    from_sql: ClassVar[str]
    """The chunk table plus the joins the filters need."""

    @abstractmethod
    def filter_clause(self, filters: FiltersT) -> FilterClause: ...

    def semantic_sql(self, filters: FiltersT) -> str:
        return self._semantic_sql(self.filter_clause(filters))

    def full_text_sql(self, filters: FiltersT) -> str:
        return self._full_text_sql(self.filter_clause(filters))

    def semantic(
        self,
        session: Session,
        query_vec: list[float],
        *,
        limit: int,
        filters: FiltersT,
    ) -> list[RankedHit]:
        clause = self.filter_clause(filters)
        params = {
            "query_vec": vector_literal(query_vec),
            "limit": limit,
            **clause.params,
        }
        return _ranked_hits(session, self._semantic_sql(clause), params)

    def full_text(
        self,
        session: Session,
        query_text: str,
        *,
        limit: int,
        filters: FiltersT,
    ) -> list[RankedHit]:
        clause = self.filter_clause(filters)
        params = {
            "fts_config": settings.retrieval_fts_config,
            "query_text": query_text,
            "limit": limit,
            **clause.params,
        }
        return _ranked_hits(session, self._full_text_sql(clause), params)

    def _semantic_sql(self, clause: FilterClause) -> str:
        c = self.chunks
        return f"""
            SELECT {c}.id,
                   1 - ({c}.embedding <=> CAST(:query_vec AS vector)) AS score
            FROM {self.from_sql}
            WHERE {c}.embedding IS NOT NULL
            {_and(clause)}
            ORDER BY {c}.embedding <=> CAST(:query_vec AS vector)
            LIMIT :limit
        """

    def _full_text_sql(self, clause: FilterClause) -> str:
        c = self.chunks
        return f"""
            SELECT {c}.id,
                   ts_rank_cd({c}.search_vector, query) AS score
            FROM {self.from_sql},
                 plainto_tsquery(CAST(:fts_config AS regconfig), :query_text) query
            WHERE {c}.search_vector @@ query
            {_and(clause)}
            ORDER BY score DESC
            LIMIT :limit
        """


def _and(clause: FilterClause) -> str:
    return f"AND {clause.sql}" if clause.sql else ""


def _ranked_hits(
    session: Session, sql: str, params: dict[str, object]
) -> list[RankedHit]:
    rows = session.execute(text(sql), params).all()
    return [
        RankedHit(
            chunk_id=UUID(str(row.id)),
            rank=index,
            score=float(row.score) if row.score is not None else None,
        )
        for index, row in enumerate(rows, start=1)
    ]

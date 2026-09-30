"""Search SQL over document_chunks joined to their filing."""

from __future__ import annotations

from pydantic import BaseModel

from app.retrieval.queries import ChunkQueries, FilterClause


class DocumentSearchFilters(BaseModel):
    ticker: str | None = None
    fiscal_years: list[int] | None = None
    form: str | None = None


class DocumentQueries(ChunkQueries[DocumentSearchFilters]):
    chunks = "dc"
    from_sql = "document_chunks dc JOIN source_documents sd ON sd.id = dc.document_id"

    def filter_clause(self, filters: DocumentSearchFilters) -> FilterClause:
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
        return FilterClause(" AND ".join(clauses), params)

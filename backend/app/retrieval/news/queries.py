"""Search SQL over news_items, always scoped to one user's active mailboxes."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.retrieval.email.queries import scope_clause
from app.retrieval.queries import ChunkQueries, FilterClause


class NewsSearchFilters(BaseModel):
    user_id: UUID
    mailbox_ids: list[UUID]
    since: date | None = None
    until: date | None = None
    big_only: bool = False


class NewsQueries(ChunkQueries[NewsSearchFilters]):
    chunks = "ni"
    from_sql = (
        "news_items ni "
        "JOIN emails e ON e.id = ni.email_id "
        "JOIN mailboxes m ON m.id = e.mailbox_id "
        "LEFT JOIN news_stories s ON s.id = ni.story_id"
    )

    def filter_clause(self, filters: NewsSearchFilters) -> FilterClause:
        scope = scope_clause(filters.user_id, filters.mailbox_ids)
        clauses = [scope.sql]
        params: dict[str, object] = dict(scope.params)
        if filters.since is not None:
            clauses.append("ni.edition_date >= :since")
            params["since"] = filters.since
        if filters.until is not None:
            clauses.append("ni.edition_date <= :until")
            params["until"] = filters.until
        if filters.big_only:
            clauses.append("s.is_big IS TRUE")
        return FilterClause(" AND ".join(clauses), params)

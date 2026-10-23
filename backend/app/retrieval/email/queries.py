"""Search SQL over email_chunks, always scoped to one user's active mailboxes."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.retrieval.queries import (
    ChunkQueries,
    FilterClause,
    RankedHit,
    _and,
    _ranked_hits,
)


class EmailSearchFilters(BaseModel):
    user_id: UUID
    mailbox_ids: list[UUID]
    since: date | None = None
    until: date | None = None
    label: str | None = None
    sender: str | None = None
    mailbox: str | None = None


def scope_clause(user_id: UUID, mailbox_ids: list[UUID]) -> FilterClause:
    """The owner scope every mail and news query repeats, including the passage load."""
    return FilterClause(
        "m.user_id = :user_id AND m.id = ANY(:mailbox_ids) AND m.is_active IS TRUE",
        {"user_id": user_id, "mailbox_ids": mailbox_ids},
    )


class EmailQueries(ChunkQueries[EmailSearchFilters]):
    chunks = "ec"
    from_sql = (
        "email_chunks ec "
        "JOIN emails e ON e.id = ec.email_id "
        "JOIN mailboxes m ON m.id = e.mailbox_id"
    )

    def filter_clause(self, filters: EmailSearchFilters) -> FilterClause:
        scope = scope_clause(filters.user_id, filters.mailbox_ids)
        clauses = [scope.sql]
        params: dict[str, object] = {
            **scope.params,
            "email_timezone": settings.email_timezone,
        }
        if filters.since is not None:
            clauses.append("(e.sent_at AT TIME ZONE :email_timezone)::date >= :since")
            params["since"] = filters.since
        if filters.until is not None:
            clauses.append("(e.sent_at AT TIME ZONE :email_timezone)::date <= :until")
            params["until"] = filters.until
        if filters.label is not None:
            clauses.append("e.label = :label")
            params["label"] = filters.label
        if filters.sender is not None:
            clauses.append(
                "(e.from_address ILIKE :sender OR e.from_name ILIKE :sender)"
            )
            params["sender"] = f"%{filters.sender}%"
        if filters.mailbox is not None:
            clauses.append(
                "(lower(m.display_name) = lower(:mailbox) OR lower(m.address) = lower(:mailbox))"
            )
            params["mailbox"] = filters.mailbox
        return FilterClause(" AND ".join(clauses), params)

    def recent_sql(self, filters: EmailSearchFilters) -> str:
        """Newest mail first, one row per email: for searches with filters but no words."""
        return f"""
            SELECT ec.id, 1.0 AS score
            FROM {self.from_sql}
            WHERE ec.chunk_index = 0
            {_and(self.filter_clause(filters))}
            ORDER BY e.sent_at DESC
            LIMIT :limit
        """

    def recent(
        self, session: Session, *, limit: int, filters: EmailSearchFilters
    ) -> list[RankedHit]:
        params = {"limit": limit, **self.filter_clause(filters).params}
        return _ranked_hits(session, self.recent_sql(filters), params)

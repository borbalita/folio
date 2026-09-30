"""Search SQL over email_chunks, always scoped to one user's active mailboxes."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.config import settings
from app.retrieval.queries import ChunkQueries, FilterClause


class EmailSearchFilters(BaseModel):
    user_id: UUID
    mailbox_ids: list[UUID]
    since: date | None = None
    until: date | None = None
    label: str | None = None
    sender: str | None = None
    mailbox: str | None = None


def scope_clause(filters: EmailSearchFilters) -> FilterClause:
    """The owner scope every mail query repeats, including the passage load."""
    return FilterClause(
        "m.user_id = :user_id AND m.id = ANY(:mailbox_ids) AND m.is_active IS TRUE",
        {"user_id": filters.user_id, "mailbox_ids": filters.mailbox_ids},
    )


class EmailQueries(ChunkQueries[EmailSearchFilters]):
    chunks = "ec"
    from_sql = (
        "email_chunks ec "
        "JOIN emails e ON e.id = ec.email_id "
        "JOIN mailboxes m ON m.id = e.mailbox_id"
    )

    def filter_clause(self, filters: EmailSearchFilters) -> FilterClause:
        scope = scope_clause(filters)
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
            clauses.append("e.from_address ILIKE :sender")
            params["sender"] = f"%{filters.sender}%"
        if filters.mailbox is not None:
            clauses.append(
                "(lower(m.display_name) = lower(:mailbox) OR lower(m.address) = lower(:mailbox))"
            )
            params["mailbox"] = filters.mailbox
        return FilterClause(" AND ".join(clauses), params)

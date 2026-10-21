"""Vector search over news_items and stories ranked by coverage. Every query repeats the owner scope."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from langfuse import get_client
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_session
from app.retrieval.email.queries import scope_clause
from app.retrieval.news.queries import NewsQueries, NewsSearchFilters
from ingest.embeddings import embed_query

_ITEMS_FROM = (
    "news_items ni "
    "JOIN emails e ON e.id = ni.email_id "
    "JOIN mailboxes m ON m.id = e.mailbox_id"
)
_ITEM_COLUMNS = (
    "ni.id, ni.story_id, ni.source, ni.edition_date, ni.title, ni.blurb, ni.url"
)


class NewsPassage(BaseModel):
    item_id: UUID
    story_id: UUID | None
    source: str
    edition_date: date
    title: str
    blurb: str
    url: str
    score: float


class Story(BaseModel):
    """A story with the user's items and its coverage: newsletters, item count, days."""

    story_id: UUID
    first_seen: date
    last_seen: date
    is_big: bool
    sources: list[str]
    item_count: int
    items: list[NewsPassage]

    @property
    def days(self) -> int:
        return (self.last_seen - self.first_seen).days + 1


def rank_stories(stories: list[Story]) -> list[Story]:
    """Big first, then more newsletters, items and days, then newest; ties by id."""
    ordered = sorted(stories, key=lambda story: story.story_id)
    return sorted(
        ordered,
        key=lambda story: (
            story.is_big,
            len(story.sources),
            story.item_count,
            story.days,
            story.last_seen,
        ),
        reverse=True,
    )


def load_news_items(
    session: Session, item_ids: list[UUID], filters: NewsSearchFilters
) -> dict[UUID, NewsPassage]:
    scope = scope_clause(filters.user_id, filters.mailbox_ids)
    rows = session.execute(
        text(
            f"""
            SELECT {_ITEM_COLUMNS}
            FROM {_ITEMS_FROM}
            WHERE ni.id = ANY(:item_ids)
              AND {scope.sql}
            """
        ),
        {"item_ids": item_ids, **scope.params},
    ).all()
    return {UUID(str(row.id)): _passage(row) for row in rows}


class NewsRetriever:
    queries = NewsQueries()

    def search(
        self,
        query: str,
        *,
        filters: NewsSearchFilters,
        session: Session | None = None,
    ) -> list[NewsPassage]:
        if not filters.mailbox_ids:
            return []
        if session is not None:
            return self._search(session, query, filters)
        with get_session() as owned:
            return self._search(owned, query, filters)

    def stories(
        self,
        *,
        filters: NewsSearchFilters,
        limit: int,
        session: Session | None = None,
    ) -> list[Story]:
        """Stories in the period, ranked by coverage, at most `limit`; `big_only` keeps big ones."""
        if not filters.mailbox_ids:
            return []
        if session is not None:
            return _stories(session, filters, limit)
        with get_session() as owned:
            return _stories(owned, filters, limit)

    def _search(
        self, session: Session, query: str, filters: NewsSearchFilters
    ) -> list[NewsPassage]:
        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="retriever",
            name="news-search",
            metadata={"top_k": settings.retrieval_top_k},
        ) as span:
            with langfuse.start_as_current_observation(
                as_type="embedding",
                name="embed-query",
                model=settings.openai_embedding_model,
            ):
                query_vec = embed_query(query)
            hits = self.queries.semantic(
                session, query_vec, limit=settings.retrieval_top_k, filters=filters
            )
            loaded = (
                load_news_items(session, [hit.chunk_id for hit in hits], filters)
                if hits
                else {}
            )
            passages = [
                loaded[hit.chunk_id].model_copy(update={"score": hit.score or 0.0})
                for hit in hits
                if hit.chunk_id in loaded
            ]
            span.update(metadata={"passage_count": len(passages)})
            return passages


def _stories(session: Session, filters: NewsSearchFilters, limit: int) -> list[Story]:
    scope = scope_clause(filters.user_id, filters.mailbox_ids)
    # Only items from the period count and are shown: "since Monday" never cites
    # last Thursday, and big means both newsletters covered it within the period.
    where = [scope.sql]
    params: dict[str, Any] = dict(scope.params)
    if filters.since is not None:
        where.append("ni.edition_date >= :since")
        params["since"] = filters.since
    if filters.until is not None:
        where.append("ni.edition_date <= :until")
        params["until"] = filters.until
    having: list[str] = []
    if filters.big_only:
        having.append("count(DISTINCT ni.source) > 1")
    having_sql = f"HAVING {' AND '.join(having)}" if having else ""
    # Stories group items from every mailbox, so big and the dates come from this
    # user's items only: another user's item never makes a story big or wider.
    aggregates = session.execute(
        text(
            f"""
            SELECT s.id,
                   min(ni.edition_date) AS first_seen,
                   max(ni.edition_date) AS last_seen,
                   count(DISTINCT ni.source) > 1 AS is_big,
                   array_agg(DISTINCT ni.source ORDER BY ni.source) AS sources,
                   count(ni.id) AS item_count
            FROM news_stories s
            JOIN {_ITEMS_FROM} ON ni.story_id = s.id
            WHERE {" AND ".join(where)}
            GROUP BY s.id
            {having_sql}
            """
        ),
        params,
    ).all()
    ranked = rank_stories([_story(row) for row in aggregates])[:limit]
    if not ranked:
        return []
    story_ids = [story.story_id for story in ranked]
    rows = session.execute(
        text(
            f"""
            SELECT {_ITEM_COLUMNS}
            FROM {_ITEMS_FROM}
            WHERE ni.story_id = ANY(:story_ids)
              AND {" AND ".join(where)}
            ORDER BY ni.source, ni.position
            """
        ),
        {"story_ids": story_ids, **params},
    ).all()
    by_id = {story.story_id: story for story in ranked}
    for row in rows:
        by_id[UUID(str(row.story_id))].items.append(_passage(row))
    return ranked


def _story(row: Any) -> Story:
    return Story(
        story_id=UUID(str(row.id)),
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        is_big=row.is_big,
        sources=list(row.sources),
        item_count=row.item_count,
        items=[],
    )


def _passage(row: Any) -> NewsPassage:
    return NewsPassage(
        item_id=UUID(str(row.id)),
        story_id=UUID(str(row.story_id)) if row.story_id is not None else None,
        source=row.source,
        edition_date=row.edition_date,
        title=row.title,
        blurb=row.blurb,
        url=row.url,
        score=0.0,
    )

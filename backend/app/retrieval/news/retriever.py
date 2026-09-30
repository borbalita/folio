"""Vector search over news_items and the big cross-source stories. Every query repeats the owner scope."""

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


class BigStory(BaseModel):
    story_id: UUID
    first_seen: date
    last_seen: date
    items: list[NewsPassage]


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

    def big_stories(
        self, *, filters: NewsSearchFilters, session: Session | None = None
    ) -> list[BigStory]:
        if not filters.mailbox_ids:
            return []
        if session is not None:
            return _big_stories(session, filters)
        with get_session() as owned:
            return _big_stories(owned, filters)

    def _search(
        self, session: Session, query: str, filters: NewsSearchFilters
    ) -> list[NewsPassage]:
        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="retriever",
            name="news-search",
            input={"query": query, "filters": filters.model_dump(mode="json")},
            metadata={"top_k": settings.retrieval_top_k},
        ) as span:
            with langfuse.start_as_current_observation(
                as_type="embedding",
                name="embed-query",
                model=settings.openai_embedding_model,
                input=query,
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
            span.update(output={"passage_count": len(passages)})
            return passages


def _big_stories(session: Session, filters: NewsSearchFilters) -> list[BigStory]:
    scope = scope_clause(filters.user_id, filters.mailbox_ids)
    story_clauses = ["s.is_big IS TRUE"]
    params: dict[str, Any] = {**scope.params, "limit": settings.retrieval_top_k}
    if filters.until is not None:
        story_clauses.append("s.first_seen <= :until")
        params["until"] = filters.until
    if filters.since is not None:
        story_clauses.append("s.last_seen >= :since")
        params["since"] = filters.since
    rows = session.execute(
        text(
            f"""
            WITH stories AS (
                SELECT s.id, s.first_seen, s.last_seen
                FROM news_stories s
                WHERE {" AND ".join(story_clauses)}
                  AND EXISTS (
                      SELECT 1 FROM {_ITEMS_FROM}
                      WHERE ni.story_id = s.id AND {scope.sql}
                  )
                ORDER BY s.last_seen DESC
                LIMIT :limit
            )
            SELECT st.first_seen, st.last_seen, {_ITEM_COLUMNS}
            FROM stories st
            JOIN {_ITEMS_FROM} ON ni.story_id = st.id
            WHERE {scope.sql}
            ORDER BY st.last_seen DESC, st.id, ni.source, ni.position
            """
        ),
        params,
    ).all()
    return _group_stories(rows)


def _group_stories(rows: Any) -> list[BigStory]:
    stories: dict[UUID, BigStory] = {}
    for row in rows:
        story_id = UUID(str(row.story_id))
        story = stories.get(story_id)
        if story is None:
            story = BigStory(
                story_id=story_id,
                first_seen=row.first_seen,
                last_seen=row.last_seen,
                items=[],
            )
            stories[story_id] = story
        story.items.append(_passage(row))
    return list(stories.values())


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

"""Hybrid search over one user's mail. Every step repeats the owner scope."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.retrieval.base import HybridRetriever
from app.retrieval.email import rerank
from app.retrieval.email.queries import EmailQueries, EmailSearchFilters, scope_clause


class EmailPassage(BaseModel):
    chunk_id: UUID
    email_id: UUID
    text: str
    from_address: str
    subject: str
    sent_at: datetime
    mailbox_name: str
    fusion_score: float


def load_passages(
    session: Session,
    chunk_ids: list[UUID],
    filters: EmailSearchFilters,
) -> dict[UUID, EmailPassage]:
    scope = scope_clause(filters.user_id, filters.mailbox_ids)
    rows = session.execute(
        text(
            f"""
            SELECT ec.id,
                   ec.email_id,
                   ec.chunk_text,
                   e.from_address,
                   e.subject,
                   e.sent_at,
                   m.display_name
            FROM email_chunks ec
            JOIN emails e ON e.id = ec.email_id
            JOIN mailboxes m ON m.id = e.mailbox_id
            WHERE ec.id = ANY(:chunk_ids)
              AND {scope.sql}
            """
        ),
        {"chunk_ids": chunk_ids, **scope.params},
    ).all()
    return {
        UUID(str(row.id)): EmailPassage(
            chunk_id=UUID(str(row.id)),
            email_id=UUID(str(row.email_id)),
            text=row.chunk_text,
            from_address=row.from_address,
            subject=row.subject,
            sent_at=row.sent_at,
            mailbox_name=row.display_name,
            fusion_score=0.0,
        )
        for row in rows
    }


class EmailRetriever(HybridRetriever[EmailSearchFilters, EmailPassage]):
    corpus = "email"
    queries = EmailQueries()
    keyword_prompt = (
        "Extract 1 to 4 keywords for Postgres full-text search over personal email. "
        "Prefer people and company names, subjects, products, services, and "
        "order or invoice numbers. Leave out dates, senders' addresses, and mail "
        "categories; they are filtered separately. "
        "No stopwords, no sentences, no punctuation."
    )

    def __init__(
        self, *, rerank: bool | None = None, judge: rerank.Judge | None = None
    ) -> None:
        """`rerank` defaults to settings.email_rerank; evals pass it to compare both."""
        self.rerank = settings.email_rerank if rerank is None else rerank
        self.judge = judge

    def search(
        self,
        query: str,
        *,
        filters: EmailSearchFilters,
        session: Session | None = None,
        question: str | None = None,
    ) -> list[EmailPassage]:
        """`question` is the user's message; tool queries are often just keywords."""
        if not filters.mailbox_ids:
            return []
        passages = super().search(query, filters=filters, session=session)
        if not self.rerank:
            return passages
        return rerank.rerank(
            passages,
            query=query,
            question=question,
            judge=self.judge or rerank.judge_with_jev,
            top_k=settings.retrieval_top_k,
        )

    def _fused_count(self) -> int:
        if self.rerank:
            return settings.email_rerank_candidates
        return settings.retrieval_top_k

    def _hydrate(
        self,
        session: Session,
        fused: list[tuple[UUID, float]],
        filters: EmailSearchFilters,
    ) -> list[EmailPassage]:
        loaded = load_passages(session, [chunk_id for chunk_id, _ in fused], filters)
        return [
            loaded[chunk_id].model_copy(update={"fusion_score": score})
            for chunk_id, score in fused
            if chunk_id in loaded
        ]

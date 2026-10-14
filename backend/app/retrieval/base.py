"""Hybrid search shared by every corpus: embed, semantic + full-text, RRF, hydrate."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar
from uuid import UUID

from langfuse import get_client
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_session
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keywords import extract_fts_keywords
from app.retrieval.queries import ChunkQueries
from ingest.embeddings import embed_query


class HybridRetriever[FiltersT: BaseModel, PassageT: BaseModel](ABC):
    corpus: ClassVar[str]
    queries: ClassVar[ChunkQueries[Any]]
    keyword_prompt: ClassVar[str]

    def search(
        self,
        query: str,
        *,
        filters: FiltersT,
        session: Session | None = None,
    ) -> list[PassageT]:
        if session is not None:
            return self._search(session, query, filters)
        with get_session() as owned:
            return self._search(owned, query, filters)

    def _search(
        self, session: Session, query: str, filters: FiltersT
    ) -> list[PassageT]:
        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="retriever",
            name="hybrid-search",
            metadata={
                "corpus": self.corpus,
                "candidate_k": settings.retrieval_candidate_k,
                "top_k": settings.retrieval_top_k,
                "rrf_k": settings.retrieval_rrf_k,
            },
        ) as span:
            with langfuse.start_as_current_observation(
                as_type="embedding",
                name="embed-query",
                model=settings.openai_embedding_model,
            ):
                query_vec = embed_query(query)

            limit = settings.retrieval_candidate_k
            semantic = self.queries.semantic(
                session, query_vec, limit=limit, filters=filters
            )
            keywords = extract_fts_keywords(query, system_prompt=self.keyword_prompt)
            full_text = self.queries.full_text(
                session, keywords, limit=limit, filters=filters
            )
            fused = reciprocal_rank_fusion(
                [
                    [hit.chunk_id for hit in semantic],
                    [hit.chunk_id for hit in full_text],
                ],
                k=settings.retrieval_rrf_k,
            )[: self._fused_count()]

            passages = self._hydrate(session, fused, filters) if fused else []
            span.update(metadata=self._span_metadata(passages))
            return passages

    def _fused_count(self) -> int:
        """How many fused hits to hydrate; more than top_k when a later step filters them."""
        return settings.retrieval_top_k

    def _span_metadata(self, passages: list[PassageT]) -> dict[str, Any]:
        return {"passage_count": len(passages)}

    @abstractmethod
    def _hydrate(
        self, session: Session, fused: list[tuple[UUID, float]], filters: FiltersT
    ) -> list[PassageT]:
        """Load passages in fused order with their fusion score. Drop ids that no longer load."""

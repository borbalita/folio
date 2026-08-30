"""Hybrid retrieval orchestrator: embed → search → fuse → hydrate."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import documents
from app.database.engine import get_session
from app.database.models import DocumentChunk, SourceDocument
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.queries import SearchFilters, full_text_search, semantic_search
from ingest.embeddings import embed_query


class RetrievedPassage(BaseModel):
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    page: str | None
    section: str | None
    fusion_score: float
    ticker: str
    company_name: str
    form: str
    filing_date: date
    fiscal_year: int
    accession_number: str
    neighbors: list[RetrievedPassage] = Field(default_factory=list)


class DocumentRetriever:
    def search(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
        include_neighbors: bool = True,
        session: Session | None = None,
    ) -> list[RetrievedPassage]:
        if session is not None:
            return self._search_with_session(
                session,
                query,
                filters=filters,
                include_neighbors=include_neighbors,
            )

        with get_session() as owned_session:
            return self._search_with_session(
                owned_session,
                query,
                filters=filters,
                include_neighbors=include_neighbors,
            )

    def _search_with_session(
        self,
        session: Session,
        query: str,
        *,
        filters: SearchFilters | None,
        include_neighbors: bool,
    ) -> list[RetrievedPassage]:
        query_vec = embed_query(query)
        semantic_hits = semantic_search(
            session,
            query_vec,
            limit=settings.retrieval_candidate_k,
            filters=filters,
        )
        fts_hits = full_text_search(
            session,
            query,
            limit=settings.retrieval_candidate_k,
            filters=filters,
        )

        fused = reciprocal_rank_fusion(
            [
                [hit.chunk_id for hit in semantic_hits],
                [hit.chunk_id for hit in fts_hits],
            ],
            k=settings.retrieval_rrf_k,
        )[:settings.retrieval_top_k]

        if not fused:
            return []

        fused_ids = [chunk_id for chunk_id, _ in fused]
        fusion_scores = dict(fused)
        chunks_by_id = documents.get_chunks_by_ids(session, fused_ids)

        passages: list[RetrievedPassage] = []
        seen_neighbor_ids: set[UUID] = set[UUID](fused_ids)

        for chunk_id in fused_ids:
            loaded = chunks_by_id.get(chunk_id)
            if loaded is None:
                continue
            chunk, document = loaded

            neighbors = (
                _neighbors_for_chunk(session, chunk_id, seen_neighbor_ids)
                if include_neighbors
                else []
            )
            passages.append(
                _passage_from_chunk(
                    chunk,
                    document,
                    fusion_score=fusion_scores[chunk_id],
                    neighbors=neighbors,
                ),
            )

        return passages


def _neighbors_for_chunk(
    session: Session,
    chunk_id: UUID,
    seen_ids: set[UUID],
) -> list[RetrievedPassage]:
    neighbors: list[RetrievedPassage] = []
    for neighbor_chunk, neighbor_document in documents.get_surrounding_chunks(
        session,
        chunk_id,
        settings.retrieval_neighbor_radius,
    ):
        if neighbor_chunk.id in seen_ids:
            continue
        seen_ids.add(neighbor_chunk.id)
        neighbors.append(
            _passage_from_chunk(
                neighbor_chunk,
                neighbor_document,
                fusion_score=0.0,
            ),
        )
    return neighbors


def _metadata_str(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _passage_from_chunk(
    chunk: DocumentChunk,
    document: SourceDocument,
    *,
    fusion_score: float,
    neighbors: list[RetrievedPassage] | None = None,
) -> RetrievedPassage:
    metadata = chunk.metadata_ or {}
    return RetrievedPassage(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        text=chunk.chunk_text,
        page=_metadata_str(metadata, "page"),
        section=_metadata_str(metadata, "section"),
        fusion_score=fusion_score,
        ticker=document.ticker,
        company_name=document.company_name,
        form=document.filing_type,
        filing_date=document.filing_date,
        fiscal_year=document.fiscal_year,
        accession_number=document.accession_number,
        neighbors=neighbors or [],
    )

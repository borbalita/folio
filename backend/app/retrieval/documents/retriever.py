"""Hybrid search over 10-K filings, with neighboring chunks attached to each hit."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import documents
from app.database.engine import get_session
from app.database.models import DocumentChunk, SourceDocument
from app.retrieval.base import HybridRetriever
from app.retrieval.documents.queries import DocumentQueries, DocumentSearchFilters


class DocumentPassage(BaseModel):
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
    neighbors: list[DocumentPassage] = Field(default_factory=list)


class DocumentRetriever(HybridRetriever[DocumentSearchFilters, DocumentPassage]):
    corpus = "documents"
    queries = DocumentQueries()
    keyword_prompt = (
        "Extract 3 to 5 keywords for Postgres full-text search over SEC 10-K filings. "
        "Prefer company names, products, segments, and financial line items. "
        "No stopwords, no sentences, no punctuation."
    )

    def passage_by_id(
        self, chunk_id: UUID, *, session: Session | None = None
    ) -> DocumentPassage | None:
        if session is not None:
            return _passage_by_id(session, chunk_id)
        with get_session() as owned:
            return _passage_by_id(owned, chunk_id)

    def surrounding_passages(
        self, chunk_id: UUID, *, session: Session | None = None
    ) -> list[DocumentPassage]:
        if session is not None:
            return _surrounding_passages(session, chunk_id)
        with get_session() as owned:
            return _surrounding_passages(owned, chunk_id)

    def _hydrate(
        self,
        session: Session,
        fused: list[tuple[UUID, float]],
        filters: DocumentSearchFilters,
    ) -> list[DocumentPassage]:
        loaded = documents.get_chunks_by_ids(
            session, [chunk_id for chunk_id, _ in fused]
        )
        seen_ids = {chunk_id for chunk_id, _ in fused}
        passages: list[DocumentPassage] = []
        for chunk_id, score in fused:
            row = loaded.get(chunk_id)
            if row is None:
                continue
            chunk, document = row
            passages.append(
                _passage(
                    chunk,
                    document,
                    fusion_score=score,
                    neighbors=_neighbors(session, chunk_id, seen_ids),
                )
            )
        return passages

    def _span_output(self, passages: list[DocumentPassage]) -> dict[str, Any]:
        return {
            "passage_count": len(passages),
            "tickers": sorted({passage.ticker for passage in passages}),
        }


def _passage_by_id(session: Session, chunk_id: UUID) -> DocumentPassage | None:
    row = documents.get_chunks_by_ids(session, [chunk_id]).get(chunk_id)
    if row is None:
        return None
    chunk, document = row
    return _passage(chunk, document, fusion_score=0.0)


def _surrounding_passages(session: Session, chunk_id: UUID) -> list[DocumentPassage]:
    return [
        _passage(chunk, document, fusion_score=0.0)
        for chunk, document in documents.get_surrounding_chunks(
            session, chunk_id, settings.retrieval_neighbor_radius
        )
    ]


def _neighbors(
    session: Session, chunk_id: UUID, seen_ids: set[UUID]
) -> list[DocumentPassage]:
    neighbors: list[DocumentPassage] = []
    for chunk, document in documents.get_surrounding_chunks(
        session, chunk_id, settings.retrieval_neighbor_radius
    ):
        if chunk.id in seen_ids:
            continue
        seen_ids.add(chunk.id)
        neighbors.append(_passage(chunk, document, fusion_score=0.0))
    return neighbors


def _metadata_str(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return None if value is None else str(value)


def _passage(
    chunk: DocumentChunk,
    document: SourceDocument,
    *,
    fusion_score: float,
    neighbors: list[DocumentPassage] | None = None,
) -> DocumentPassage:
    metadata = chunk.metadata_ or {}
    return DocumentPassage(
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

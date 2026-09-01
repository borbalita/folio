"""Source document and chunk persistence for ingestion via SQLAlchemy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.database.engine import get_session_factory
from app.database.models import DocumentChunk, MessageCitation, SourceDocument


@dataclass(frozen=True, slots=True)
class FilingRecord:
    ticker: str
    form: str
    filing_date: date
    report_date: date
    accession_number: str
    source_url: str
    html_path: Path
    markdown_path: Path
    company_name: str

    @property
    def fiscal_year(self) -> int:
        return self.report_date.year


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_index: int
    chunk_text: str
    token_count: int
    metadata: dict[str, Any]


def document_by_accession(
    session: Session,
    accession_number: str,
) -> SourceDocument | None:
    return session.scalar(
        select(SourceDocument).where(
            SourceDocument.accession_number == accession_number,
        ),
    )


def document_has_chunks(session: Session, document_id: uuid.UUID) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id),
    )
    return bool(count)


def delete_chunks(session: Session, document_id: uuid.UUID) -> None:
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
    session.execute(
        delete(MessageCitation).where(MessageCitation.chunk_id.in_(chunk_ids)),
    )
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id),
    )


def upsert_source_document(
    session: Session,
    filing: FilingRecord,
    markdown_content: str,
) -> SourceDocument:
    existing = document_by_accession(session, filing.accession_number)
    fields = {
        "ticker": filing.ticker,
        "company_name": filing.company_name,
        "filing_type": filing.form,
        "filing_date": filing.filing_date,
        "fiscal_year": filing.fiscal_year,
        "accession_number": filing.accession_number,
        "source_url": filing.source_url,
        "markdown_content": markdown_content,
    }
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    document = SourceDocument(**fields)
    session.add(document)
    session.flush()
    return document


def insert_document_chunks(
    session: Session,
    document_id: uuid.UUID,
    records: list[ChunkRecord],
    embeddings: list[list[float]],
) -> None:
    if len(records) != len(embeddings):
        msg = "records and embeddings length mismatch"
        raise ValueError(msg)

    for record, embedding in zip(records, embeddings, strict=True):
        session.add(
            DocumentChunk(
                document_id=document_id,
                chunk_index=record.chunk_index,
                chunk_text=record.chunk_text,
                token_count=record.token_count,
                metadata_=record.metadata,
                embedding=embedding,
            ),
        )


def get_chunks_by_ids(
    session: Session,
    chunk_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[DocumentChunk, SourceDocument]]:
    if not chunk_ids:
        return {}

    rows = session.execute(
        select(DocumentChunk, SourceDocument).join(
            SourceDocument,
            SourceDocument.id == DocumentChunk.document_id,
        ).where(DocumentChunk.id.in_(chunk_ids)),
    ).all()
    return {chunk.id: (chunk, document) for chunk, document in rows}


def get_surrounding_chunks(
    session: Session,
    chunk_id: uuid.UUID,
    radius: int,
) -> list[tuple[DocumentChunk, SourceDocument]]:
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None or radius <= 0:
        return []

    rows = session.execute(
        select(DocumentChunk, SourceDocument)
        .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
        .where(
            and_(
                DocumentChunk.document_id == chunk.document_id,
                DocumentChunk.chunk_index >= chunk.chunk_index - radius,
                DocumentChunk.chunk_index <= chunk.chunk_index + radius,
                DocumentChunk.id != chunk_id,
            ),
        )
        .order_by(DocumentChunk.chunk_index),
    ).all()
    return list(rows)


def session_scope() -> Session:
    return get_session_factory()()

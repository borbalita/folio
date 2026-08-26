"""Source document and chunk persistence for ingestion via SQLAlchemy."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database.engine import get_session_factory
from app.database.models import DocumentChunk, MessageCitation, SourceDocument
from ingest.chunking import ChunkRecord
from ingest.manifest import FilingRecord


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


def session_scope() -> Session:
    return get_session_factory()()

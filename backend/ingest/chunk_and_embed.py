"""Chunk SEC HTML filings, embed chunks, and store them in document_chunks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import structlog

from app.database import documents
from app.database.models import SourceDocument
from app.logging import configure_logging
from ingest.chunking import CHUNK_MAX_TOKENS, chunk_document, iter_all_html_paths
from ingest.embeddings import EMBED_BATCH_SIZE, embed_texts
from ingest.manifest import load_manifest

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestCounts:
    processed: int = 0
    skipped: int = 0
    chunks_written: int = 0


def _filing_metadata(document: SourceDocument) -> dict[str, object]:
    return {
        "ticker": document.ticker,
        "company_name": document.company_name,
        "filing_type": document.filing_type,
        "filing_date": document.filing_date.isoformat(),
        "fiscal_year": document.fiscal_year,
        "accession_number": document.accession_number,
        "source_url": document.source_url,
    }


def ingest_document(
    session,
    document: SourceDocument,
    html_path,
    *,
    max_chunks: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    if force and not dry_run:
        documents.delete_chunks(session, document.id)
        log.info("chunks_deleted_for_reingest", accession_number=document.accession_number)

    if not dry_run and not force and documents.document_has_chunks(session, document.id):
        log.info("filing_skipped", accession_number=document.accession_number, reason="has_chunks")
        return 0

    if not html_path.is_file():
        log.error(
            "filing_missing_html",
            accession_number=document.accession_number,
            html_path=str(html_path),
        )
        return 0

    records = chunk_document(
        html_path,
        _filing_metadata(document),
        max_chunks=max_chunks,
    )
    if not records:
        log.warning("filing_empty", accession_number=document.accession_number)
        return 0

    max_tokens = max(record.token_count for record in records)
    log.info(
        "filing_chunked",
        accession_number=document.accession_number,
        chunk_count=len(records),
        max_tokens=max_tokens,
        chunk_limit=CHUNK_MAX_TOKENS,
    )

    if dry_run:
        sample = records[0]
        log.info(
            "dry_run_sample",
            accession_number=document.accession_number,
            section=sample.metadata.get("section"),
            preview=sample.chunk_text[:120],
        )
        return len(records)

    vectors = embed_texts([record.chunk_text for record in records])
    documents.insert_document_chunks(session, document.id, records, vectors)
    session.commit()

    log.info(
        "filing_ingested",
        accession_number=document.accession_number,
        ticker=document.ticker,
        chunk_count=len(records),
        embed_batch_size=EMBED_BATCH_SIZE,
    )
    return len(records)


def ingest_accessions(
    accessions: list[str],
    *,
    max_chunks: int | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> IngestCounts:
    filings_by_accession = {filing.accession_number: filing for filing in load_manifest()}
    counts = IngestCounts()

    with documents.session_scope() as session:
        for accession in accessions:
            document = documents.document_by_accession(session, accession)
            if document is None:
                msg = (
                    f"No source_document for accession {accession}. "
                    "Run `uv run python -m ingest.load_source_documents` first."
                )
                raise ValueError(msg)

            filing = filings_by_accession.get(accession)
            if filing is None:
                raise ValueError(f"Accession {accession} not found in manifest")

            if (
                not dry_run
                and not force
                and skip_existing
                and documents.document_has_chunks(session, document.id)
            ):
                log.info("filing_skipped", accession_number=accession, reason="has_chunks")
                counts = IngestCounts(
                    processed=counts.processed,
                    skipped=counts.skipped + 1,
                    chunks_written=counts.chunks_written,
                )
                continue

            written = ingest_document(
                session,
                document,
                filing.html_path,
                max_chunks=max_chunks,
                dry_run=dry_run,
                force=force,
            )
            counts = IngestCounts(
                processed=counts.processed + 1,
                skipped=counts.skipped,
                chunks_written=counts.chunks_written + written,
            )

    log.info(
        "chunk_and_embed_finished",
        processed=counts.processed,
        skipped=counts.skipped,
        chunks_written=counts.chunks_written,
    )
    return counts


def ingest_all(
    *,
    max_chunks: int | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> IngestCounts:
    accessions = [accession for accession, _ in iter_all_html_paths()]
    return ingest_accessions(
        accessions,
        max_chunks=max_chunks,
        dry_run=dry_run,
        skip_existing=skip_existing,
        force=force,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--accession", help="Process one filing by accession number")
    target.add_argument("--all", action="store_true", help="Process all manifest filings")
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Cap chunks per document (use 1 for smoke test)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk only; no embeddings or database writes",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip documents that already have chunks (default: true)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing chunks for target document(s) before re-ingesting",
    )
    return parser


def main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if args.all:
        ingest_all(
            max_chunks=args.max_chunks,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            force=args.force,
        )
    else:
        ingest_accessions(
            [args.accession],
            max_chunks=args.max_chunks,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            force=args.force,
        )


if __name__ == "__main__":
    main()

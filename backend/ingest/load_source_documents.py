"""Load normalized Markdown filings into source_documents."""

from __future__ import annotations

from pathlib import Path

import argparse

import structlog

from app.database import documents
from app.logging import configure_logging
from ingest.manifest import DEFAULT_MANIFEST_PATH, load_manifest

log = structlog.get_logger(__name__)


def load_source_documents(
    *,
    manifest_path=DEFAULT_MANIFEST_PATH,
    skip_existing: bool = True,
) -> dict[str, int]:
    filings = load_manifest(manifest_path)
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "missing": 0}

    with documents.session_scope() as session:
        for filing in filings:
            if not filing.markdown_path.is_file():
                log.error(
                    "filing_missing_markdown",
                    accession_number=filing.accession_number,
                    markdown_path=str(filing.markdown_path),
                )
                counts["missing"] += 1
                continue

            existing = documents.document_by_accession(session, filing.accession_number)
            if existing is not None and skip_existing:
                log.info(
                    "source_document_skipped",
                    accession_number=filing.accession_number,
                    reason="already_exists",
                )
                counts["skipped"] += 1
                continue

            markdown = filing.markdown_path.read_text(encoding="utf-8")
            was_existing = existing is not None
            documents.upsert_source_document(session, filing, markdown)
            if was_existing:
                counts["updated"] += 1
                log.info("source_document_updated", accession_number=filing.accession_number)
            else:
                counts["inserted"] += 1
                log.info("source_document_inserted", accession_number=filing.accession_number)

        session.commit()

    log.info("load_source_documents_finished", total=len(filings), **counts)
    return counts


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to data/downloads/manifest.json",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip filings already present in source_documents (default: true)",
    )
    args = parser.parse_args()
    load_source_documents(
        manifest_path=args.manifest,
        skip_existing=args.skip_existing,
    )


if __name__ == "__main__":
    main()

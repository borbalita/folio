from __future__ import annotations

from pathlib import Path

import pytest

from ingest.chunking import (
    CHUNK_MAX_TOKENS,
    EMBEDDING_MAX_TOKENS,
    chunk_document,
    count_tokens,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
MINIMAL_FILING_HTML = FIXTURES_DIR / "minimal_filing.htm"


def test_count_tokens() -> None:
    assert count_tokens("one two three") >= 3
    assert count_tokens("") == 1


def test_chunk_max_tokens_constant() -> None:
    assert CHUNK_MAX_TOKENS == 512
    assert EMBEDDING_MAX_TOKENS == 8192


@pytest.mark.integration
def test_chunk_document_hierarchical() -> None:
    metadata = {"ticker": "TEST", "accession_number": "acc-1"}
    records = chunk_document(MINIMAL_FILING_HTML, metadata)
    assert records
    assert all(record.chunk_text.strip() for record in records)
    assert all(record.token_count <= EMBEDDING_MAX_TOKENS for record in records)
    assert records[0].metadata["ticker"] == "TEST"
    sections = {record.metadata.get("section") for record in records if record.metadata.get("section")}
    assert "Item 1. Business" in sections or "Item 1A. Risk Factors" in sections

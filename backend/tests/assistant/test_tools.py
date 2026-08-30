from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock
from uuid import UUID

from app.assistant.deps import DocumentAgentDeps
from app.assistant.tools import (
    execute_read_chunk,
    execute_read_surrounding_chunks,
    execute_search_filings,
)
from app.retrieval.retriever import DocumentRetriever, RetrievedPassage

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")
THREAD = UUID("00000000-0000-0000-0000-0000000000aa")
USER = UUID("00000000-0000-0000-0000-000000000001")
DOC = UUID("00000000-0000-0000-0000-00000000000d")


def _passage(**overrides: object) -> RetrievedPassage:
    values: dict[str, object] = {
        "chunk_id": A,
        "document_id": DOC,
        "chunk_index": 0,
        "text": "Services revenue increased.",
        "page": "12",
        "section": "Item 1",
        "fusion_score": 0.02,
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "form": "10-K",
        "filing_date": date(2023, 11, 3),
        "fiscal_year": 2023,
        "accession_number": "0000320193-23-000106",
        "neighbors": [],
    }
    values.update(overrides)
    return RetrievedPassage.model_validate(values)


def _deps(retriever: DocumentRetriever | MagicMock | None = None) -> DocumentAgentDeps:
    return DocumentAgentDeps(
        user_id=USER,
        thread_id=THREAD,
        retriever=retriever or MagicMock(),
    )


def test_search_filings_registers_hits_and_neighbors() -> None:
    neighbor = _passage(chunk_id=B, chunk_index=1, text="Neighbor passage.")
    hit = _passage(neighbors=[neighbor])
    retriever = MagicMock()
    retriever.search.return_value = [hit]
    deps = _deps(retriever)

    output = execute_search_filings(deps, "Apple Services", ticker="AAPL")

    retriever.search.assert_called_once()
    assert A in deps.seen_ids
    assert B in deps.seen_ids
    assert str(A) in output
    assert "Neighbor passage." in output


def test_read_chunk_registers_id() -> None:
    retriever = MagicMock()
    retriever.passage_by_id.return_value = _passage()
    deps = _deps(retriever)

    output = execute_read_chunk(deps, A)

    assert A in deps.seen_ids
    assert "Services revenue increased." in output


def test_read_chunk_missing_does_not_register() -> None:
    retriever = MagicMock()
    retriever.passage_by_id.return_value = None
    deps = _deps(retriever)

    output = execute_read_chunk(deps, A)

    assert deps.seen_ids == set()
    assert output == "No matching passages found in the filing corpus."


def test_read_surrounding_registers_neighbors() -> None:
    neighbor = _passage(chunk_id=B, chunk_index=1, text="Around the hit.")
    retriever = MagicMock()
    retriever.surrounding_passages.return_value = [neighbor]
    deps = _deps(retriever)

    output = execute_read_surrounding_chunks(deps, A)

    assert B in deps.seen_ids
    assert A not in deps.seen_ids
    assert "Around the hit." in output

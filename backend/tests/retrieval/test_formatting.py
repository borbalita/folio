from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.retrieval.formatting import (
    MAX_PASSAGE_EXCERPT_CHARS,
    format_passages_for_agent,
)
from app.retrieval.retriever import RetrievedPassage

CHUNK_A = UUID("00000000-0000-0000-0000-00000000000a")
DOC_A = UUID("00000000-0000-0000-0000-00000000000d")


def _passage(**overrides: object) -> RetrievedPassage:
    values: dict[str, object] = {
        "chunk_id": CHUNK_A,
        "document_id": DOC_A,
        "chunk_index": 0,
        "text": "Services revenue increased.",
        "page": None,
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


def test_empty_passages() -> None:
    assert format_passages_for_agent([]) == (
        "No matching passages found in the filing corpus."
    )


def test_excerpt_is_truncated() -> None:
    long_text = "x" * (MAX_PASSAGE_EXCERPT_CHARS + 50)
    output = format_passages_for_agent([_passage(text=long_text)])
    assert "..." in output
    assert str(CHUNK_A) in output
    assert "AAPL 10-K FY2023" in output


def test_total_output_stays_within_character_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.retrieval.formatting.MAX_AGENT_OUTPUT_CHARS", 80)
    output = format_passages_for_agent([_passage(text="Services revenue increased.")])
    assert len(output) == 80
    assert output.endswith("...")


def test_neighbors_included() -> None:
    neighbor = _passage(
        chunk_id=UUID("00000000-0000-0000-0000-00000000000b"),
        chunk_index=1,
        text="Neighbor passage.",
        fusion_score=0.0,
    )
    output = format_passages_for_agent([_passage(neighbors=[neighbor])])
    assert "neighbor idx=1" in output
    assert "Neighbor passage." in output

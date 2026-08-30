from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.retrieval.queries import RankedChunkHit
from app.retrieval.retriever import DocumentRetriever

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")
C = UUID("00000000-0000-0000-0000-00000000000c")
DOC = UUID("00000000-0000-0000-0000-00000000000d")


def _chunk(chunk_id: UUID, index: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=chunk_id,
        document_id=DOC,
        chunk_index=index,
        chunk_text=text,
        metadata_={"section": "Item 1", "page": "12"},
    )


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="AAPL",
        company_name="Apple Inc.",
        filing_type="10-K",
        filing_date=date(2023, 11, 3),
        fiscal_year=2023,
        accession_number="0000320193-23-000106",
    )


def test_retriever_fuses_and_attaches_neighbors(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _document()
    chunks = {
        A: (_chunk(A, 0, "Hit A"), document),
        B: (_chunk(B, 1, "Hit B"), document),
    }
    neighbor = _chunk(C, 2, "Neighbor C")

    monkeypatch.setattr(
        "app.retrieval.retriever.embed_query",
        lambda _query: [0.1, 0.2],
    )
    monkeypatch.setattr(
        "app.retrieval.retriever.semantic_search",
        lambda *_args, **_kwargs: [
            RankedChunkHit(chunk_id=A, rank=1, score=0.9),
            RankedChunkHit(chunk_id=B, rank=2, score=0.8),
        ],
    )
    monkeypatch.setattr(
        "app.retrieval.retriever.full_text_search",
        lambda *_args, **_kwargs: [
            RankedChunkHit(chunk_id=A, rank=1, score=0.5),
        ],
    )
    monkeypatch.setattr(
        "app.retrieval.retriever.documents.get_chunks_by_ids",
        lambda _session, _ids: chunks,
    )

    def fake_neighbors(_session, chunk_id: UUID, _radius: int):
        if chunk_id == A:
            return [(neighbor, document)]
        return []

    monkeypatch.setattr(
        "app.retrieval.retriever.documents.get_surrounding_chunks",
        fake_neighbors,
    )

    passages = DocumentRetriever().search("Apple Services revenue", session=object())

    assert [p.chunk_id for p in passages] == [A, B]
    assert passages[0].fusion_score > passages[1].fusion_score
    assert passages[0].section == "Item 1"
    assert passages[0].page == "12"
    assert passages[0].form == "10-K"
    assert len(passages[0].neighbors) == 1
    assert passages[0].neighbors[0].chunk_id == C
    assert passages[1].neighbors == []


def test_retriever_returns_empty_when_no_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.retrieval.retriever.embed_query", lambda _query: [0.1])
    monkeypatch.setattr(
        "app.retrieval.retriever.semantic_search",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.retrieval.retriever.full_text_search",
        lambda *_args, **_kwargs: [],
    )

    assert DocumentRetriever().search("nothing", session=object()) == []

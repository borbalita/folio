from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.retrieval.base import HybridRetriever
from app.retrieval.queries import RankedHit

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")


class _Filters(BaseModel):
    pass


class _Passage(BaseModel):
    chunk_id: UUID
    fusion_score: float


class _Queries:
    def __init__(self, semantic: list[RankedHit], full_text: list[RankedHit]) -> None:
        self._semantic = semantic
        self._full_text = full_text
        self.full_text_query = ""

    def semantic(self, *_args: object, **_kwargs: object) -> list[RankedHit]:
        return self._semantic

    def full_text(
        self, _session: object, query_text: str, **_kwargs: object
    ) -> list[RankedHit]:
        self.full_text_query = query_text
        return self._full_text


class _Retriever(HybridRetriever[_Filters, _Passage]):
    corpus = "test"
    keyword_prompt = "test prompt"

    def __init__(self, queries: _Queries) -> None:
        self.queries = queries  # type: ignore[misc]
        self.hydrated: list[tuple[UUID, float]] | None = None

    def _hydrate(
        self, session: Session, fused: list[tuple[UUID, float]], filters: _Filters
    ) -> list[_Passage]:
        self.hydrated = fused
        return [
            _Passage(chunk_id=chunk_id, fusion_score=score) for chunk_id, score in fused
        ]


@pytest.fixture(autouse=True)
def _no_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.retrieval.base.embed_query", lambda _query: [0.1])


@pytest.fixture(autouse=True)
def prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def extract(query: str, *, system_prompt: str) -> str:
        seen.append(system_prompt)
        return query.upper()

    monkeypatch.setattr("app.retrieval.base.extract_fts_keywords", extract)
    return seen


def _hit(chunk_id: UUID, rank: int) -> RankedHit:
    return RankedHit(chunk_id=chunk_id, rank=rank)


def test_no_hits_returns_empty_without_hydrating() -> None:
    retriever = _Retriever(_Queries([], []))

    assert retriever.search("q", filters=_Filters(), session=object()) == []
    assert retriever.hydrated is None


def test_fused_order_and_scores_reach_hydrate() -> None:
    retriever = _Retriever(_Queries([_hit(A, 1), _hit(B, 2)], [_hit(B, 1)]))

    passages = retriever.search("q", filters=_Filters(), session=object())

    assert [passage.chunk_id for passage in passages] == [B, A]
    assert passages[0].fusion_score > passages[1].fusion_score
    assert retriever.hydrated == [(p.chunk_id, p.fusion_score) for p in passages]


def test_full_text_gets_keywords_from_the_subclass_prompt(prompts: list[str]) -> None:
    queries = _Queries([], [])

    _Retriever(queries).search("rent", filters=_Filters(), session=object())

    assert prompts == ["test prompt"]
    assert queries.full_text_query == "RENT"

"""Code-computed scores. Retrieval metrics are at email level, not chunk level."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel


class RetrievalScores(BaseModel):
    """None means not applicable: a case with no expected email has no recall, precision, or MRR."""

    recall: float | None
    precision: float | None
    mrr: float | None
    first_relevant_rank: int | None


def emails_in_rank_order(
    chunk_ids: Iterable[UUID], email_key_by_chunk: dict[UUID, str]
) -> list[str]:
    """Collapse ranked chunks to ranked emails, each at the rank of its first chunk."""
    ranked: list[str] = []
    for chunk_id in chunk_ids:
        key = email_key_by_chunk[chunk_id]
        if key not in ranked:
            ranked.append(key)
    return ranked


def retrieval_scores(
    ranked_keys: list[str], expected_keys: list[str], k: int
) -> RetrievalScores:
    """Recall@k and MRR over expected emails; precision@k over the emails actually returned.

    Precision divides by returned emails, not by k: with one expected email, hits / k could
    never exceed 1 / k.
    """
    if not expected_keys:
        return RetrievalScores(
            recall=None, precision=None, mrr=None, first_relevant_rank=None
        )
    top = ranked_keys[:k]
    expected = set(expected_keys)
    hits = [rank for rank, key in enumerate(top, start=1) if key in expected]
    first = hits[0] if hits else None
    return RetrievalScores(
        recall=len(hits) / len(expected),
        precision=len(hits) / len(top) if top else 0.0,
        mrr=1 / first if first else 0.0,
        first_relevant_rank=first,
    )


def mean(values: Iterable[float | None]) -> float | None:
    """Average of the applicable values; None when nothing applies."""
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None

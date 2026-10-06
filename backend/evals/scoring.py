"""Code-computed scores. Retrieval metrics are at email level, not chunk level."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel


class RetrievalScores(BaseModel):
    """None means not applicable: a case with no expected email has no recall, precision, or MRR;
    `empty` applies only to such cases, and `distractor_rate` only to cases with distractors."""

    recall: float | None
    recall_at_3: float | None
    precision: float | None
    mrr: float | None
    first_relevant_rank: int | None
    distractor_rate: float | None
    """Share of the case's planned distractors (outdated values, look-alikes) returned in the top k."""
    empty: float | None
    """1.0 when an unanswerable search returns nothing, else 0.0."""


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
    ranked_keys: list[str], expected_keys: list[str], distractor_keys: list[str], k: int
) -> RetrievalScores:
    """Recall@k, recall@3, and MRR over expected emails; precision@k over the emails returned.

    Precision divides by returned emails, not by k: with one expected email, hits / k could
    never exceed 1 / k.
    """
    top = ranked_keys[:k]
    distractor_rate = (
        len(set(top) & set(distractor_keys)) / len(set(distractor_keys))
        if distractor_keys
        else None
    )
    if not expected_keys:
        return RetrievalScores(
            recall=None,
            recall_at_3=None,
            precision=None,
            mrr=None,
            first_relevant_rank=None,
            distractor_rate=distractor_rate,
            empty=0.0 if top else 1.0,
        )
    expected = set(expected_keys)
    hits = [rank for rank, key in enumerate(top, start=1) if key in expected]
    first = hits[0] if hits else None
    return RetrievalScores(
        recall=len(hits) / len(expected),
        recall_at_3=sum(1 for rank in hits if rank <= 3) / len(expected),
        precision=len(hits) / len(top) if top else 0.0,
        mrr=1 / first if first else 0.0,
        first_relevant_rank=first,
        distractor_rate=distractor_rate,
        empty=None,
    )


def mean(values: Iterable[float | None]) -> float | None:
    """Average of the applicable values; None when nothing applies."""
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None

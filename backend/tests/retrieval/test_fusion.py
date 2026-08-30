from __future__ import annotations

from uuid import UUID

from app.retrieval.fusion import reciprocal_rank_fusion

A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")
C = UUID("00000000-0000-0000-0000-00000000000c")


def test_empty_rankings() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_single_hit_score() -> None:
    assert reciprocal_rank_fusion([[A]], k=60) == [(A, 1.0 / 61)]


def test_overlapping_lists_prefer_shared_hits() -> None:
    fused = reciprocal_rank_fusion([[A, B], [A, C]], k=60)
    assert [chunk_id for chunk_id, _ in fused] == [A, B, C]


def test_shared_lower_rank_beats_unique_top_hit() -> None:
    fused = reciprocal_rank_fusion([[A], [B, C], [B, C]], k=60)
    assert fused[0][0] == B


def test_default_k_is_60() -> None:
    assert reciprocal_rank_fusion([[A]]) == reciprocal_rank_fusion([[A]], k=60)

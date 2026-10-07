from __future__ import annotations

from uuid import UUID

import pytest

from evals.scoring import emails_in_rank_order, mean, retrieval_scores


def _chunk(n: int) -> UUID:
    return UUID(int=n)


def test_chunks_collapse_to_emails_at_their_first_rank() -> None:
    owners = {_chunk(1): "e02", _chunk(2): "e01", _chunk(3): "e02", _chunk(4): "e03"}

    ranked = emails_in_rank_order([_chunk(1), _chunk(2), _chunk(3), _chunk(4)], owners)

    assert ranked == ["e02", "e01", "e03"]


def test_scores_for_an_expected_email_at_rank_two() -> None:
    scores = retrieval_scores(["e09", "e01", "e05", "e07"], ["e01"], [], k=10)

    assert scores.recall == 1.0
    assert scores.precision == 0.25
    assert scores.mrr == 0.5
    assert scores.first_relevant_rank == 2


def test_only_the_top_k_emails_count() -> None:
    scores = retrieval_scores(["e09", "e05", "e01"], ["e01", "e02"], [], k=2)

    assert (scores.recall, scores.precision, scores.mrr) == (0.0, 0.0, 0.0)
    assert scores.first_relevant_rank is None


def test_partial_recall_with_two_expected_emails() -> None:
    scores = retrieval_scores(["e01", "e09"], ["e01", "e02"], [], k=10)

    assert (scores.recall, scores.precision, scores.mrr) == (0.5, 0.5, 1.0)


def test_no_results_score_zero() -> None:
    scores = retrieval_scores([], ["e01"], [], k=10)

    assert (scores.recall, scores.precision, scores.mrr) == (0.0, 0.0, 0.0)


def test_no_expected_emails_is_not_applicable() -> None:
    scores = retrieval_scores(["e01"], [], [], k=10)

    assert (scores.recall, scores.precision, scores.mrr) == (None, None, None)


def test_mean_ignores_not_applicable_values() -> None:
    assert mean([1.0, None, 0.0]) == pytest.approx(0.5)
    assert mean([None]) is None


def test_recall_at_3_counts_only_the_top_three() -> None:
    scores = retrieval_scores(["e01", "e09", "e08", "e02"], ["e01", "e02"], [], k=10)

    assert scores.recall == 1.0
    assert scores.recall_at_3 == 0.5


def test_distractor_rate_is_the_share_of_planned_distractors_returned() -> None:
    scores = retrieval_scores(
        ["e01", "e05", "e06", "e07"], ["e01"], ["e05", "e08"], k=10
    )

    assert scores.distractor_rate == 0.5


def test_distractors_beyond_k_are_not_counted() -> None:
    scores = retrieval_scores(["e01", "e02", "e05"], ["e01"], ["e05"], k=2)

    assert scores.distractor_rate == 0.0


def test_no_planned_distractors_is_not_applicable() -> None:
    assert retrieval_scores(["e01"], ["e01"], [], k=10).distractor_rate is None


def test_empty_applies_only_to_unanswerable_cases() -> None:
    assert retrieval_scores([], [], ["e05"], k=10).empty == 1.0
    assert retrieval_scores(["e05"], [], ["e05"], k=10).empty == 0.0
    assert retrieval_scores([], ["e01"], [], k=10).empty is None


def test_unanswerable_case_still_scores_distractors() -> None:
    scores = retrieval_scores(["e05", "e09"], [], ["e05"], k=10)

    assert (scores.recall, scores.precision, scores.mrr) == (None, None, None)
    assert scores.distractor_rate == 1.0

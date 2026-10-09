from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError

from app.config import Settings, settings
from app.retrieval.email import rerank
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailPassage, EmailRetriever
from app.retrieval.queries import RankedHit
from tests.conftest import span_text

USER = UUID("00000000-0000-0000-0000-000000000001")
MAILBOX = UUID("00000000-0000-0000-0000-000000000010")


def _passage(n: int, subject: str | None = None) -> EmailPassage:
    return EmailPassage(
        chunk_id=UUID(int=n),
        email_id=UUID(int=1000 + n),
        text=f"Body {n}",
        from_address=f"sender{n}@example.com",
        subject=subject or f"Subject {n}",
        sent_at=datetime(2026, 9, n, 8, 0, tzinfo=UTC),
        mailbox_name="Yahoo",
        fusion_score=1 / n,
    )


def _judge_by_subject(verdicts: dict[str, rerank.Evidence | None]) -> rerank.Judge:
    async def judge(prompt: str) -> rerank.Evidence | None:
        subject = next(
            line.removeprefix("Subject: ")
            for line in prompt.splitlines()
            if line.startswith("Subject: ")
        )
        return verdicts[subject]

    return judge


def _always(verdict: rerank.Evidence | None) -> rerank.Judge:
    async def judge(_prompt: str) -> rerank.Evidence | None:
        return verdict

    return judge


def _subjects(passages: list[EmailPassage]) -> list[str]:
    return [p.subject for p in passages]


def test_full_comes_before_partial_each_in_fused_order_and_none_is_dropped() -> None:
    passages = [_passage(n) for n in range(1, 6)]
    judge = _judge_by_subject(
        {
            "Subject 1": "partial",
            "Subject 2": "none",
            "Subject 3": "full",
            "Subject 4": "partial",
            "Subject 5": "full",
        }
    )

    result = rerank.rerank(passages, query="q", question=None, judge=judge, top_k=10)

    assert _subjects(result) == ["Subject 3", "Subject 5", "Subject 1", "Subject 4"]


def test_result_is_capped_at_top_k() -> None:
    passages = [_passage(n) for n in range(1, 6)]

    result = rerank.rerank(
        passages, query="q", question=None, judge=_always("full"), top_k=2
    )

    assert _subjects(result) == ["Subject 1", "Subject 2"]


def test_nothing_survives_when_every_passage_has_no_evidence() -> None:
    passages = [_passage(n) for n in range(1, 4)]

    result = rerank.rerank(
        passages, query="q", question=None, judge=_always("none"), top_k=10
    )

    assert result == []


def test_an_outage_keeps_plain_fused_order() -> None:
    passages = [_passage(n) for n in range(1, 13)]

    result = rerank.rerank(
        passages, query="q", question=None, judge=_always(None), top_k=10
    )

    assert result == passages[:10]


def test_a_failed_judgement_ranks_with_partial_in_fused_order() -> None:
    passages = [_passage(n) for n in range(1, 4)]
    judge = _judge_by_subject(
        {"Subject 1": "partial", "Subject 2": None, "Subject 3": "full"}
    )

    result = rerank.rerank(passages, query="q", question=None, judge=judge, top_k=10)

    assert _subjects(result) == ["Subject 3", "Subject 1", "Subject 2"]


def test_judge_sees_question_query_and_email() -> None:
    prompt = rerank.judge_input(
        "landlord radiator", "When is the radiator visit?", _passage(4, "Radiator")
    )

    assert "The person asked: When is the radiator visit?" in prompt
    assert "Search: landlord radiator" in prompt
    assert "From: sender4@example.com" in prompt
    assert "Subject: Radiator" in prompt
    assert "Date: 2026-09-04" in prompt
    assert "Body 4" in prompt


def test_judge_input_without_question_only_has_the_search() -> None:
    prompt = rerank.judge_input("rent", None, _passage(1))

    assert "The person asked" not in prompt
    assert prompt.startswith("Search: rent")


def test_jev_model_error_is_a_failed_judgement() -> None:
    class _Failing:
        async def run(self, _prompt: str) -> None:
            raise ModelHTTPError(status_code=503, model_name="jev")

    assert asyncio.run(rerank.judge_with_jev(_Failing(), "anything")) is None  # type: ignore[arg-type]


def _patch_search(monkeypatch: pytest.MonkeyPatch, count: int) -> list[int]:
    """Fuse `count` hits; record how many the retriever hydrates."""
    hydrated: list[int] = []
    hits = [
        RankedHit(chunk_id=UUID(int=n), rank=n, score=1.0) for n in range(1, count + 1)
    ]
    monkeypatch.setattr("app.retrieval.base.embed_query", lambda _query: [0.1])
    monkeypatch.setattr(
        "app.retrieval.base.extract_fts_keywords", lambda query, *, system_prompt: query
    )
    monkeypatch.setattr(
        "app.retrieval.email.queries.EmailQueries.semantic", lambda *_a, **_k: hits
    )
    monkeypatch.setattr(
        "app.retrieval.email.queries.EmailQueries.full_text", lambda *_a, **_k: []
    )

    def load(_session: object, ids: list[UUID], _filters: object) -> dict:
        hydrated.append(len(ids))
        return {chunk_id: _passage(chunk_id.int % 28 + 1) for chunk_id in ids}

    monkeypatch.setattr("app.retrieval.email.retriever.load_passages", load)
    return hydrated


def _filters() -> EmailSearchFilters:
    return EmailSearchFilters(user_id=USER, mailbox_ids=[MAILBOX])


def test_reranking_judges_more_candidates_and_passes_the_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hydrated = _patch_search(monkeypatch, 30)
    prompts: list[str] = []

    async def judge(prompt: str) -> rerank.Evidence:
        prompts.append(prompt)
        return "full"

    found = EmailRetriever(rerank=True, judge=judge).search(
        "radiator", filters=_filters(), session=object(), question="When is it?"
    )

    assert hydrated == [settings.email_rerank_candidates]
    assert len(prompts) == settings.email_rerank_candidates
    assert all("The person asked: When is it?" in p for p in prompts)
    assert len(found) == settings.retrieval_top_k


def test_reranking_off_is_plain_hybrid_search(monkeypatch: pytest.MonkeyPatch) -> None:
    hydrated = _patch_search(monkeypatch, 30)

    async def judge(_prompt: str) -> rerank.Evidence:
        raise AssertionError("judge should not run")

    found = EmailRetriever(rerank=False, judge=judge).search(
        "radiator", filters=_filters(), session=object()
    )

    assert hydrated == [settings.retrieval_top_k]
    assert len(found) == settings.retrieval_top_k


def test_reranking_without_a_typesafe_key_fails_at_startup() -> None:
    values = settings.model_dump() | {"email_rerank": True, "typesafe_api_key": None}

    with pytest.raises(ValidationError, match="EMAIL_RERANK needs TYPESAFE_API_KEY"):
        Settings.model_validate(values)


def test_rerank_span_keeps_counts_not_query(
    langfuse_spans: Callable[[], tuple],
) -> None:
    passages = [_passage(n) for n in range(1, 4)]
    judge = _judge_by_subject(
        {"Subject 1": "full", "Subject 2": "none", "Subject 3": None}
    )

    rerank.rerank(
        passages, query="SECRET-Q", question="SECRET-QQ", judge=judge, top_k=10
    )

    exported = span_text(langfuse_spans(), "rerank")
    assert "SECRET" not in exported
    for count, value in (("candidates", 3), ("kept", 2), ("dropped", 1), ("failed", 1)):
        assert f"'langfuse.observation.metadata.{count}': {value}" in exported

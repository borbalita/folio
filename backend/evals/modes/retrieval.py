"""Retrieval test: the real email search with each case's fixed probe; no chat model involved."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from langfuse import Evaluation, Langfuse
from pydantic import BaseModel

from app.config import settings
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailRetriever
from evals.cases import RagCase
from evals.dataset import IdMap, load_id_map, load_rag_cases
from evals.experiment import RunConfig, publication, run_experiment
from evals.langfuse_sync import item_id, local_rag_payloads, rag_dataset_name
from evals.scoring import (
    RetrievalScores,
    emails_in_rank_order,
    mean,
    retrieval_scores,
)


class RetrievalResult(BaseModel):
    case_id: str
    kind: str
    split: str
    answerable: bool
    expected_email_keys: list[str]
    retrieved_email_keys: list[str]
    distractors_retrieved: list[str]
    scores: RetrievalScores


def chunk_owners(id_map: IdMap) -> dict[UUID, str]:
    return {
        chunk_id: key
        for key, ids in id_map.emails.items()
        for chunk_id in ids.chunk_ids
    }


def run_case(case: RagCase, owners: dict[UUID, str]) -> RetrievalResult:
    filters = EmailSearchFilters(
        user_id=case.user_id,
        mailbox_ids=[case.mailbox_id],
        **case.probe_filters.model_dump(),
    )
    passages = EmailRetriever().search(case.probe_query, filters=filters)
    ranked = emails_in_rank_order((p.chunk_id for p in passages), owners)
    return RetrievalResult(
        case_id=case.case_id,
        kind=case.kind,
        split=case.split,
        answerable=case.answerable,
        expected_email_keys=case.expected_email_keys,
        retrieved_email_keys=ranked,
        distractors_retrieved=[key for key in ranked if key in case.distractor_keys],
        scores=retrieval_scores(
            ranked,
            case.expected_email_keys,
            case.distractor_keys,
            k=settings.retrieval_top_k,
        ),
    )


METRICS = ("recall", "recall_at_3", "precision", "mrr", "distractor_rate", "empty")


def summarize(results: list[RetrievalResult]) -> dict[str, object]:
    """Averages overall and per case kind; each metric over the cases it applies to."""

    def averages(group: list[RetrievalResult]) -> dict[str, float | None]:
        return {m: mean(getattr(r.scores, m) for r in group) for m in METRICS}

    by_kind: dict[str, list[RetrievalResult]] = defaultdict(list)
    for result in results:
        by_kind[result.kind].append(result)
    return {
        "cases": len(results),
        "unanswerable_cases": sum(1 for r in results if not r.answerable),
        "overall": averages(results),
        "by_kind": {kind: averages(group) for kind, group in sorted(by_kind.items())},
        "distractor_retrieved_cases": sum(
            1 for r in results if r.distractors_retrieved
        ),
    }


def retrieval_evaluations(result: RetrievalResult) -> list[Evaluation]:
    """One score per applicable metric; nothing for a metric that doesn't apply, never a fake 1.0."""
    comment = f"retrieved {result.retrieved_email_keys}, expected {result.expected_email_keys}"
    return [
        Evaluation(name=metric, value=value, comment=comment)
        for metric in METRICS
        if (value := getattr(result.scores, metric)) is not None
    ]


def run(client: Langfuse, version: str, concurrency: int) -> dict[str, object]:
    cases = load_rag_cases(version)
    dataset_name = rag_dataset_name(version)
    by_item = {item_id(dataset_name, case.case_id): case for case in cases}
    owners = chunk_owners(load_id_map(version))

    async def task(key: str) -> RetrievalResult:
        result = await asyncio.to_thread(run_case, by_item[key], owners)
        print(f"  {result.case_id} {result.kind:14} {_scores_line(result)}")
        return result

    config = RunConfig(
        mode="retrieval",
        version=version,
        subject=f"email-search ({settings.openai_embedding_model}, keywords {settings.openai_chat_model})",
        today=cases[0].today,
        prompts={"keyword_prompt": EmailRetriever.keyword_prompt},
        concurrency=concurrency,
    )
    experiment = run_experiment(
        client,
        dataset_name=dataset_name,
        local=local_rag_payloads(version),
        config=config,
        run_name=f"retrieval {version} {datetime.now(UTC):%Y-%m-%d %H:%M:%S}",
        task=task,
        scores=retrieval_evaluations,
    )
    ordered = [experiment.results[key] for key in by_item if key in experiment.results]
    return {
        "top_k": settings.retrieval_top_k,
        "summary": summarize(ordered),
        "publication": publication(experiment),
        "results": [result.model_dump(mode="json") for result in ordered],
    }


def _scores_line(result: RetrievalResult) -> str:
    s = result.scores
    distractors = f"distractors {_format(s.distractor_rate)}"
    if not result.answerable:
        return f"unanswerable, {len(result.retrieved_email_keys)} emails returned  {distractors}"
    return (
        f"recall {s.recall:.2f}  recall@3 {s.recall_at_3:.2f}  precision {s.precision:.2f}  "
        f"mrr {s.mrr:.2f}  {distractors}"
    )


def print_summary(summary: dict[str, object]) -> None:
    print(f"\n{summary['cases']} cases, {summary['unanswerable_cases']} unanswerable")
    for name, averages in [
        ("overall", summary["overall"]),
        *summary["by_kind"].items(),
    ]:
        print(
            f"  {name:15} " + "  ".join(f"{m} {_format(averages[m])}" for m in METRICS)
        )


def _format(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"

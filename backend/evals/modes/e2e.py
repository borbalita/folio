"""End-to-end run: the real agent chooses its own searches over the real email index."""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from langfuse import Evaluation, Langfuse
from pydantic import BaseModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from sqlalchemy.orm import Session

from app.config import settings
from app.email_assistant.agent import INSTRUCTIONS_PATH
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.rerank import EvidenceJudgement
from app.retrieval.email.retriever import EmailPassage, EmailRetriever
from app.retrieval.news.retriever import NewsRetriever
from evals.agent_run import ToolStep, candidate_model, effort_settings, run_agent
from evals.cases import RagCase
from evals.dataset import IdMap, load_id_map, load_rag_cases
from evals.experiment import RunConfig, publication, run_experiment
from evals.langfuse_sync import item_id, local_rag_payloads, rag_dataset_name
from evals.modes import answer
from evals.modes.answer import chunks_of
from evals.modes.retrieval import chunk_owners
from evals.scoring import (
    AnswerScores,
    answer_scores,
    emails_in_rank_order,
    mean,
    search_recall,
)


class SearchCall(BaseModel):
    """One email search the agent made: its query and filters, and the emails returned in order."""

    query: str
    since: date | None
    until: date | None
    label: str | None
    sender: str | None
    mailbox: str | None
    email_keys: list[str]


class RecordingRetriever(EmailRetriever):
    """The real email search, keeping every call the agent made."""

    def __init__(self, owners: dict[UUID, str], *, rerank: bool) -> None:
        super().__init__(rerank=rerank)
        self.owners = owners
        self.calls: list[SearchCall] = []

    def search(
        self,
        query: str,
        *,
        filters: EmailSearchFilters,
        session: Session | None = None,
        question: str | None = None,
    ) -> list[EmailPassage]:
        passages = super().search(
            query, filters=filters, session=session, question=question
        )
        self.calls.append(
            SearchCall(
                query=query,
                since=filters.since,
                until=filters.until,
                label=filters.label,
                sender=filters.sender,
                mailbox=filters.mailbox,
                email_keys=emails_in_rank_order(
                    (p.chunk_id for p in passages), self.owners
                ),
            )
        )
        return passages


class E2EResult(BaseModel):
    case_id: str
    kind: str
    split: str
    answerable: bool
    expected_email_keys: list[str]
    searches: list[SearchCall]
    search_recall: float | None
    """Share of expected emails returned by any of the agent's searches; None if none expected."""
    answer: EmailAnswer
    cited_email_keys: list[str]
    steps: list[ToolStep]
    usage: dict[str, int]
    seconds: float
    scores: AnswerScores


async def run_case(
    case: RagCase,
    id_map: IdMap,
    owners: dict[UUID, str],
    model: Model,
    model_settings: OpenAIResponsesModelSettings | None,
    *,
    rerank: bool,
) -> E2EResult:
    retriever = RecordingRetriever(owners, rerank=rerank)
    deps = EmailAgentDeps(
        user_id=case.user_id,
        thread_id=uuid.uuid4(),
        retriever=retriever,
        news=NewsRetriever(),
    )
    started = time.perf_counter()
    record = await run_agent(case.question, case.today, deps, model, model_settings)
    seconds = time.perf_counter() - started
    cited = [c.chunk_id for c in record.answer.citations]
    return E2EResult(
        case_id=case.case_id,
        kind=case.kind,
        split=case.split,
        answerable=case.answerable,
        expected_email_keys=case.expected_email_keys,
        searches=retriever.calls,
        search_recall=search_recall(
            [call.email_keys for call in retriever.calls], case.expected_email_keys
        ),
        answer=record.answer,
        cited_email_keys=list(dict.fromkeys(owners[c] for c in cited if c in owners)),
        steps=record.steps,
        usage=record.usage,
        seconds=seconds,
        scores=answer_scores(
            record.answer,
            answerable=case.answerable,
            expected_chunk_ids=chunks_of(case.expected_email_keys, id_map),
            # Only distractors the search returned: the metric applies when they were in the evidence.
            distractor_chunk_ids=chunks_of(case.distractor_keys, id_map)
            & deps.seen_ids,
            seen_ids=deps.seen_ids,
        ),
    )


def summarize(results: Sequence[E2EResult]) -> dict[str, object]:
    """The answer test's summary plus search recall and the number of searches."""
    by_kind: dict[str, list[E2EResult]] = defaultdict(list)
    for result in results:
        by_kind[result.kind].append(result)
    summary = answer.summarize(results)
    summary["search_recall"] = {
        "overall": mean(r.search_recall for r in results),
        **{
            kind: mean(r.search_recall for r in group)
            for kind, group in sorted(by_kind.items())
        },
    }
    summary["searches_mean"] = sum(len(r.searches) for r in results) / len(results)
    summary["no_search_cases"] = [r.case_id for r in results if not r.searches]
    return summary


def e2e_evaluations(result: E2EResult) -> list[Evaluation]:
    evaluations = answer.answer_evaluations(result)
    if result.search_recall is not None:
        evaluations.append(
            Evaluation(
                name="search_recall",
                value=result.search_recall,
                comment=_searches_comment(result),
            )
        )
    return evaluations


def _searches_comment(result: E2EResult) -> str:
    if not result.searches:
        return f"no searches; expected {result.expected_email_keys}"
    lines = []
    for call in result.searches:
        filters = call.model_dump(
            mode="json", exclude={"query", "email_keys"}, exclude_none=True
        )
        lines.append(f"{call.query!r} {json.dumps(filters)} -> {call.email_keys}")
    return f"expected {result.expected_email_keys}\n" + "\n".join(lines)


def run(
    client: Langfuse,
    version: str,
    concurrency: int,
    *,
    model: str,
    effort: str | None,
    rerank: bool,
) -> dict[str, object]:
    cases = load_rag_cases(version)
    dataset_name = rag_dataset_name(version)
    by_item = {item_id(dataset_name, case.case_id): case for case in cases}
    id_map = load_id_map(version)
    owners = chunk_owners(id_map)
    chat = candidate_model(model)
    model_settings = effort_settings(effort)

    async def task(key: str) -> E2EResult:
        result = await run_case(
            by_item[key], id_map, owners, chat, model_settings, rerank=rerank
        )
        recall = (
            "n/a" if result.search_recall is None else f"{result.search_recall:.2f}"
        )
        print(
            f"  {result.case_id} {result.kind:14} {len(result.searches)} searches  "
            f"search_recall {recall}  {answer.scores_line(result)}"
        )
        return result

    prompts = {"instructions": INSTRUCTIONS_PATH.read_text(encoding="utf-8")}
    search = "no rerank"
    if rerank:
        search = (
            f"rerank {settings.typesafe_label_model}, "
            f"{settings.email_rerank_candidates} candidates"
        )
        prompts["rerank_schema"] = json.dumps(
            EvidenceJudgement.model_json_schema(), sort_keys=True
        )
    config = RunConfig(
        mode="e2e",
        version=version,
        subject=(
            f"{model} (effort {effort or 'default'}, Responses API), "
            f"email-search {search}"
        ),
        today=cases[0].today,
        prompts=prompts,
        concurrency=concurrency,
    )
    experiment = run_experiment(
        client,
        dataset_name=dataset_name,
        local=local_rag_payloads(version),
        config=config,
        run_name=(
            f"e2e {version} {model} effort-{effort or 'default'} "
            f"rerank-{'on' if rerank else 'off'} {datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
        ),
        task=task,
        scores=e2e_evaluations,
    )
    ordered = [experiment.results[key] for key in by_item if key in experiment.results]
    return {
        "model": model,
        "effort": effort,
        "rerank": rerank,
        "top_k": settings.retrieval_top_k,
        "summary": summarize(ordered) if ordered else {"cases": 0},
        "publication": publication(experiment),
        "results": [result.model_dump(mode="json") for result in ordered],
    }


def print_summary(summary: dict[str, object]) -> None:
    answer.print_summary(summary)
    if not summary["cases"]:
        return
    recall = summary["search_recall"]
    assert isinstance(recall, dict)
    print(
        f"  searches {summary['searches_mean']:.1f} per case; "
        f"no search in {summary['no_search_cases'] or 'none'}"
    )
    print(
        "  search_recall  "
        + "  ".join(
            f"{name} {'n/a' if value is None else f'{value:.3f}'}"
            for name, value in recall.items()
        )
    )

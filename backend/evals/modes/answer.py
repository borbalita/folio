"""Answer test: the real agent answers from preset evidence; search is replayed, not measured."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from langfuse import Evaluation, Langfuse
from pydantic import BaseModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from app.database.engine import get_session
from app.email_assistant.agent import INSTRUCTIONS_PATH
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer
from app.retrieval.email.retriever import EmailPassage
from app.retrieval.news.retriever import NewsRetriever
from evals.agent_run import ToolStep, candidate_model, effort_settings, run_agent
from evals.cases import RagCase
from evals.dataset import IdMap, load_id_map, load_rag_cases
from evals.experiment import RunConfig, publication, run_experiment
from evals.judge import JudgeScores, judge_answer, rubric_prompts
from evals.langfuse_sync import item_id, local_rag_payloads, rag_dataset_name
from evals.modes.retrieval import chunk_owners
from evals.replay import ReplayRetriever, evidence_email_keys, load_evidence
from evals.scoring import AnswerScores, answer_scores, mean


class AnswerResult(BaseModel):
    case_id: str
    kind: str
    split: str
    answerable: bool
    evidence_email_keys: list[str]
    """What the replayed search returned, in order: expected emails and distractors."""
    answer: EmailAnswer
    cited_email_keys: list[str]
    steps: list[ToolStep]
    usage: dict[str, int]
    seconds: float
    scores: AnswerScores
    judge: JudgeScores | None
    """None when the run had no judge."""


class ScoredAnswer(Protocol):
    """What the answer and end-to-end results share, so they summarize and score alike."""

    kind: str
    answerable: bool
    cited_email_keys: list[str]
    usage: dict[str, int]
    seconds: float
    scores: AnswerScores
    judge: JudgeScores | None


METRICS = ("refusal_correct", "evidence_cited", "distractor_cited", "grounding_pass")
JUDGE_METRICS = ("faithfulness", "fact_recall")


def metric(result: ScoredAnswer, name: str) -> float | None:
    if name in JUDGE_METRICS:
        return getattr(result.judge, name) if result.judge else None
    return getattr(result.scores, name)


async def judged(
    case: RagCase, deps: EmailAgentDeps, answer: EmailAnswer, judge: Model | None
) -> JudgeScores | None:
    if judge is None:
        return None
    return await judge_answer(
        case.question,
        answer,
        deps.seen_passages,
        case.expected_facts,
        answerable=case.answerable,
        model=judge,
    )


def chunks_of(keys: list[str], id_map: IdMap) -> set[UUID]:
    return {chunk_id for key in keys for chunk_id in id_map.emails[key].chunk_ids}


def _load_evidence(case: RagCase, id_map: IdMap) -> list[EmailPassage]:
    with get_session() as session:
        return load_evidence(session, case, id_map)


async def run_case(
    case: RagCase,
    id_map: IdMap,
    owners: dict[UUID, str],
    model: Model,
    model_settings: OpenAIResponsesModelSettings | None,
    judge: Model | None,
) -> AnswerResult:
    passages = await asyncio.to_thread(_load_evidence, case, id_map)
    deps = EmailAgentDeps(
        user_id=case.user_id,
        thread_id=uuid.uuid4(),
        retriever=ReplayRetriever(passages),
        news=NewsRetriever(),
    )
    started = time.perf_counter()
    record = await run_agent(case.question, case.today, deps, model, model_settings)
    seconds = time.perf_counter() - started
    cited = [c.chunk_id for c in record.answer.citations]
    return AnswerResult(
        case_id=case.case_id,
        kind=case.kind,
        split=case.split,
        answerable=case.answerable,
        evidence_email_keys=evidence_email_keys(case),
        answer=record.answer,
        cited_email_keys=list(dict.fromkeys(owners[c] for c in cited if c in owners)),
        steps=record.steps,
        usage=record.usage,
        seconds=seconds,
        scores=answer_scores(
            record.answer,
            answerable=case.answerable,
            expected_chunk_ids=chunks_of(case.expected_email_keys, id_map),
            distractor_chunk_ids=chunks_of(case.distractor_keys, id_map),
            seen_ids=deps.seen_ids,
        ),
        judge=await judged(case, deps, record.answer, judge),
    )


def summarize(results: Sequence[ScoredAnswer]) -> dict[str, object]:
    """Averages overall and per case kind; each metric over the cases it applies to."""

    def averages(group: Sequence[ScoredAnswer]) -> dict[str, float | None]:
        return {m: mean(metric(r, m) for r in group) for m in METRICS + JUDGE_METRICS}

    by_kind: dict[str, list[ScoredAnswer]] = defaultdict(list)
    for result in results:
        by_kind[result.kind].append(result)
    return {
        "cases": len(results),
        "unanswerable_cases": sum(1 for r in results if not r.answerable),
        "overall": averages(results),
        "by_kind": {kind: averages(group) for kind, group in sorted(by_kind.items())},
        "refusal_outcomes": dict(Counter(r.scores.refusal_outcome for r in results)),
        "grounding_errors": dict(
            Counter(
                r.scores.grounding_error for r in results if r.scores.grounding_error
            )
        ),
        "judge_errors": sum(
            1
            for r in results
            if r.judge and (r.judge.support_error or r.judge.facts_error)
        ),
        "tokens": {
            key: sum(r.usage[key] for r in results)
            for key in ("input_tokens", "output_tokens")
        },
        "seconds_mean": sum(r.seconds for r in results) / len(results),
    }


def answer_evaluations(result: ScoredAnswer) -> list[Evaluation]:
    """One score per applicable metric; nothing for a metric that doesn't apply."""
    comments = {
        "refusal_correct": result.scores.refusal_outcome,
        "evidence_cited": f"cited {result.cited_email_keys}",
        "distractor_cited": f"cited {result.cited_email_keys}",
        "grounding_pass": result.scores.grounding_error or "ok",
    }
    evaluations = [
        Evaluation(name=name, value=value, comment=comments[name])
        for name in METRICS
        if (value := getattr(result.scores, name)) is not None
    ]
    if result.judge is not None:
        evaluations.extend(judge_evaluations(result.judge))
    return evaluations


def judge_evaluations(judge: JudgeScores) -> list[Evaluation]:
    """Per-claim and per-fact reasons go in the comment; a failed call is a judge_error, never 0."""
    evaluations = []
    if judge.faithfulness is not None and judge.support is not None:
        lines = [f"{c.verdict}: {c.claim} ({c.reason})" for c in judge.support.claims]
        evaluations.append(
            Evaluation(
                name="faithfulness", value=judge.faithfulness, comment="\n".join(lines)
            )
        )
    if judge.fact_recall is not None and judge.facts is not None:
        lines = [f"{f.verdict}: {f.name} ({f.reason})" for f in judge.facts.facts]
        evaluations.append(
            Evaluation(
                name="fact_recall", value=judge.fact_recall, comment="\n".join(lines)
            )
        )
    errors = [e for e in (judge.support_error, judge.facts_error) if e]
    if errors:
        evaluations.append(
            Evaluation(name="judge_error", value=1.0, comment="\n".join(errors))
        )
    return evaluations


def run(
    client: Langfuse,
    version: str,
    concurrency: int,
    *,
    model: str,
    effort: str | None,
    judge: Model | None,
) -> dict[str, object]:
    cases = load_rag_cases(version)
    dataset_name = rag_dataset_name(version)
    by_item = {item_id(dataset_name, case.case_id): case for case in cases}
    id_map = load_id_map(version)
    owners = chunk_owners(id_map)
    chat = candidate_model(model)
    model_settings = effort_settings(effort)
    subject = f"{model} (effort {effort or 'default'}, Responses API)" + judge_note(
        judge
    )

    async def task(key: str) -> AnswerResult:
        result = await run_case(
            by_item[key], id_map, owners, chat, model_settings, judge
        )
        print(f"  {result.case_id} {result.kind:14} {scores_line(result)}")
        return result

    config = RunConfig(
        mode="answer",
        version=version,
        subject=subject,
        today=cases[0].today,
        prompts={
            "instructions": INSTRUCTIONS_PATH.read_text(encoding="utf-8"),
            **(rubric_prompts() if judge else {}),
        },
        concurrency=concurrency,
    )
    experiment = run_experiment(
        client,
        dataset_name=dataset_name,
        local=local_rag_payloads(version),
        config=config,
        run_name=(
            f"answer {version} {model} effort-{effort or 'default'} "
            f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
        ),
        task=task,
        scores=answer_evaluations,
    )
    ordered = [experiment.results[key] for key in by_item if key in experiment.results]
    return {
        "model": model,
        "effort": effort,
        "summary": summarize(ordered) if ordered else {"cases": 0},
        "publication": publication(experiment),
        "results": [result.model_dump(mode="json") for result in ordered],
    }


def judge_note(judge: Model | None) -> str:
    return f", judge {judge.model_name}" if judge else ", no judge"


def scores_line(result: ScoredAnswer) -> str:
    s = result.scores
    parts = [s.refusal_outcome]
    if s.evidence_cited is not None:
        parts.append(f"evidence {s.evidence_cited:.0f}")
    if s.distractor_cited is not None:
        parts.append(f"distractor {s.distractor_cited:.0f}")
    if s.grounding_pass is not None:
        parts.append(f"grounding {s.grounding_error or 'ok'}")
    if result.judge is not None:
        for name in JUDGE_METRICS:
            if (value := getattr(result.judge, name)) is not None:
                parts.append(f"{name} {value:.2f}")
        if result.judge.support_error or result.judge.facts_error:
            parts.append("judge_error")
    return (
        "  ".join(parts) + f"  cited {result.cited_email_keys}  {result.seconds:.1f}s"
    )


def print_summary(summary: dict[str, object]) -> None:
    if not summary["cases"]:
        print("\nno cases finished")
        return
    print(
        f"\n{summary['cases']} cases, {summary['unanswerable_cases']} unanswerable; "
        f"refusals {summary['refusal_outcomes']}; grounding errors {summary['grounding_errors']}; "
        f"judge errors {summary['judge_errors']}; "
        f"tokens {summary['tokens']}; {summary['seconds_mean']:.1f}s per case"
    )
    for name, averages in [
        ("overall", summary["overall"]),
        *summary["by_kind"].items(),
    ]:
        print(
            f"  {name:15} "
            + "  ".join(
                f"{m} {'n/a' if averages[m] is None else f'{averages[m]:.3f}'}"
                for m in METRICS + JUDGE_METRICS
            )
        )

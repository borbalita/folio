"""LLM judge for answers: claim support against cited passages, and expected facts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.config import settings
from app.email_assistant.outputs import EmailAnswer
from app.retrieval.email.retriever import EmailPassage
from app.retrieval.news.retriever import NewsPassage
from evals.scenario import Fact

JUDGE_MODEL = "claude-sonnet-5-5"
RUBRICS = Path(__file__).parent / "rubrics"
SUPPORT_RUBRIC = (RUBRICS / "support.md").read_text(encoding="utf-8")
FACTS_RUBRIC = (RUBRICS / "facts.md").read_text(encoding="utf-8")


class JudgeNotConfiguredError(RuntimeError):
    pass


class ClaimVerdict(BaseModel):
    claim: str
    reason: str
    verdict: Literal["supported", "not_supported"]


class SupportJudgement(BaseModel):
    claims: list[ClaimVerdict]


class FactVerdict(BaseModel):
    name: str
    reason: str
    verdict: Literal["correct", "wrong", "missing"]


class FactsJudgement(BaseModel):
    facts: list[FactVerdict]


class JudgeScores(BaseModel):
    """None: not applicable, or the call failed (then its error is set)."""

    faithfulness: float | None
    """Supported claims / claims; for any answer that isn't a refusal."""
    fact_recall: float | None
    """Expected facts stated correctly / expected facts; for answerable cases answered."""
    support: SupportJudgement | None = None
    facts: FactsJudgement | None = None
    support_error: str | None = None
    facts_error: str | None = None


def judge_model() -> Model:
    if not settings.anthropic_api_key:
        raise JudgeNotConfiguredError(
            "ANTHROPIC_API_KEY is required for the judge; pass --no-judge to skip it"
        )
    return AnthropicModel(
        JUDGE_MODEL, provider=AnthropicProvider(api_key=settings.anthropic_api_key)
    )


def rubric_prompts() -> dict[str, str]:
    """For the run metadata, which keeps their hashes."""
    return {"rubric_support": SUPPORT_RUBRIC, "rubric_facts": FACTS_RUBRIC}


async def judge_answer(
    question: str,
    answer: EmailAnswer,
    passages: dict[UUID, EmailPassage | NewsPassage],
    expected_facts: list[Fact],
    *,
    answerable: bool,
    model: Model,
) -> JudgeScores:
    """Two independent calls; a refusal has nothing to judge."""
    if answer.insufficient_evidence:
        return JudgeScores(faithfulness=None, fact_recall=None)
    support_call = _ask(
        model,
        SUPPORT_RUBRIC,
        support_prompt(question, answer, passages),
        SupportJudgement,
    )
    facts_call = (
        _ask(
            model,
            FACTS_RUBRIC,
            facts_prompt(question, answer, expected_facts),
            FactsJudgement,
        )
        if answerable and expected_facts
        else None
    )
    support, facts = await asyncio.gather(support_call, facts_call or _nothing())
    scores = JudgeScores(faithfulness=None, fact_recall=None)
    if isinstance(support, SupportJudgement):
        scores.support = support
        scores.faithfulness = faithfulness(support)
    elif support is not None:
        scores.support_error = support
    if isinstance(facts, FactsJudgement):
        if len(facts.facts) != len(expected_facts):
            scores.facts_error = (
                f"judged {len(facts.facts)} facts, expected {len(expected_facts)}"
            )
        else:
            scores.facts = facts
            scores.fact_recall = fact_recall(facts)
    elif facts is not None:
        scores.facts_error = facts
    return scores


def faithfulness(judgement: SupportJudgement) -> float | None:
    claims = judgement.claims
    if not claims:
        return None
    return sum(c.verdict == "supported" for c in claims) / len(claims)


def fact_recall(judgement: FactsJudgement) -> float:
    return sum(f.verdict == "correct" for f in judgement.facts) / len(judgement.facts)


async def _ask[T: BaseModel](
    model: Model, rubric: str, prompt: str, schema: type[T]
) -> T | str:
    """The judgement, or the error as text: a failed call is recorded, never scored."""
    agent = Agent(model, output_type=NativeOutput(schema), instructions=rubric)
    try:
        run = await agent.run(prompt)
    except Exception as exc:  # noqa: BLE001 - any failure is the judge's error, kept per case
        return f"{type(exc).__name__}: {exc}"
    return run.output


async def _nothing() -> None:
    return None


def support_prompt(
    question: str,
    answer: EmailAnswer,
    passages: dict[UUID, EmailPassage | NewsPassage],
) -> str:
    cited = [
        f'<passage n="{c.citation_index}">\n{_data(_render(passages[c.chunk_id]))}\n</passage>'
        for c in answer.citations
        if c.chunk_id in passages
    ]
    return (
        _block("question", question)
        + "\n"
        + _block("answer", answer.answer)
        + "\n<cited_passages>\n"
        + "\n".join(cited)
        + "\n</cited_passages>"
    )


def facts_prompt(question: str, answer: EmailAnswer, expected_facts: list[Fact]) -> str:
    facts = [
        f'<fact name="{_data(f.name)}">{_data(f.value)}</fact>' for f in expected_facts
    ]
    return (
        _block("question", question)
        + "\n"
        + _block("answer", answer.answer)
        + "\n<expected_facts>\n"
        + "\n".join(facts)
        + "\n</expected_facts>"
    )


def _block(tag: str, text: str) -> str:
    return f"<{tag}>\n{_data(text)}\n</{tag}>"


def _data(text: str) -> str:
    """Escape so data can't open or close a tag of the prompt."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _render(passage: EmailPassage | NewsPassage) -> str:
    if isinstance(passage, EmailPassage):
        return (
            f"From: {passage.from_address}\nSubject: {passage.subject}\n"
            f"Date: {passage.sent_at:%Y-%m-%d}\n\n{passage.text}"
        )
    return (
        f"News ({passage.source}, {passage.edition_date}): {passage.title}\n"
        f"{passage.blurb}\n{passage.url}"
    )

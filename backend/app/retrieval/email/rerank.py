"""Jev judges each candidate passage for evidence; full first, then partial, none dropped."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Literal

import structlog
from langfuse import get_client
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior
from pydantic_ai.models.typesafe import TypeSafeModel
from pydantic_ai.providers.typesafe import TypeSafeProvider

from app.config import settings

if TYPE_CHECKING:
    from app.retrieval.email.retriever import EmailPassage

log = structlog.get_logger(__name__)

Evidence = Literal["full", "partial", "none"]
Judge = Callable[[str], Awaitable[Evidence | None]]
"""Takes the judge input, returns a verdict or None on failure. Tests inject one; Jev otherwise."""

# Single-value literals keep each option's description in the schema Jev sees.
_EvidenceOption = (
    Annotated[
        Literal["full"],
        Field(description="The email states something the person is asking for."),
    ]
    | Annotated[
        Literal["partial"],
        Field(
            description=(
                "The email is about the same matter (same person, company, order, "
                "or event) but does not state what is asked."
            )
        ),
    ]
    | Annotated[
        Literal["none"],
        Field(
            description=(
                "The email is unrelated, or about a different person, company, "
                "order, event, or period than the one asked about."
            )
        ),
    ]
)

# A failed judgement ranks with partial: fused order is kept, so an outage degrades to
# plain hybrid search instead of an empty result.
_GROUP = {"full": 0, "partial": 1, None: 1}


class EvidenceJudgement(BaseModel):
    """Does this email contain evidence for what the person is searching their mail for?"""

    evidence: _EvidenceOption = Field(
        description="How much evidence does this email give?"
    )


def rerank(
    passages: list[EmailPassage],
    *,
    query: str,
    question: str | None,
    top_k: int,
    judge: Judge | None = None,
) -> list[EmailPassage]:
    """Sync, like the rest of search: callers run it off the event loop (the agent tool does)."""
    langfuse = get_client()
    with langfuse.start_as_current_observation(
        as_type="span",
        name="rerank",
        input={"query": query, "question": question, "candidates": len(passages)},
        metadata={"model": settings.typesafe_label_model, "top_k": top_k},
    ) as span:
        prompts = [judge_input(query, question, passage) for passage in passages]
        verdicts = asyncio.run(_judge_all(prompts, judge)) if prompts else []
        kept = sorted(
            (
                (_GROUP[verdict], position, passage)
                for position, (passage, verdict) in enumerate(
                    zip(passages, verdicts, strict=True)
                )
                if verdict != "none"
            ),
            key=lambda row: row[:2],
        )
        result = [passage for _, _, passage in kept][:top_k]
        span.update(
            output={
                "kept": len(result),
                "dropped": verdicts.count("none"),
                "failed": verdicts.count(None),
                "verdicts": [
                    {"subject": p.subject, "evidence": v}
                    for p, v in zip(passages, verdicts, strict=True)
                ],
            }
        )
        return result


def judge_input(query: str, question: str | None, passage: EmailPassage) -> str:
    asked = f"The person asked: {question}\n" if question else ""
    return (
        f"{asked}Search: {query}\n\n"
        f"From: {passage.from_address}\n"
        f"Subject: {passage.subject}\n"
        f"Date: {passage.sent_at.date().isoformat()}\n\n"
        f"{passage.text}"
    )


async def _judge_all(prompts: list[str], judge: Judge | None) -> list[Evidence | None]:
    if judge is not None:
        return list(await asyncio.gather(*map(judge, prompts)))
    # A fresh agent per search: its HTTP client belongs to this event loop, and
    # `async with` closes it before asyncio.run tears the loop down.
    agent = _judge_agent()
    async with agent:
        return list(
            await asyncio.gather(*(judge_with_jev(agent, prompt) for prompt in prompts))
        )


async def judge_with_jev(
    agent: Agent[None, EvidenceJudgement], prompt: str
) -> Evidence | None:
    try:
        result = await agent.run(prompt)
    except (AgentRunError, UnexpectedModelBehavior) as exc:
        log.warning("email_rerank_model_error", error=type(exc).__name__)
        return None
    return result.output.evidence


def _judge_agent() -> Agent[None, EvidenceJudgement]:
    model = TypeSafeModel(
        settings.typesafe_label_model,
        provider=TypeSafeProvider(api_key=settings.typesafe_api_key),
    )
    return Agent(model, output_type=EvidenceJudgement)

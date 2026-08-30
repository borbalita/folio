"""Coordinates one chat turn: agent, grounding, stream, persist."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from pydantic_ai.exceptions import AgentRunError, ModelAPIError, UnexpectedModelBehavior

from app.assistant.agent import run_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.grounding import GroundingError, validate_grounded_answer
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.messages import (
    assistant_message_for_storage,
    extract_latest_user_text,
    user_message_for_storage,
)
from app.chat.streaming import format_error, iter_grounded_stream
from app.database import chats
from app.retrieval.retriever import DocumentRetriever

log = structlog.get_logger(__name__)


def _citation_stream_payloads(answer: GroundedAnswer, deps: DocumentAgentDeps) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for citation in answer.citations:
        payload: dict[str, Any] = {
            "chunkId": str(citation.chunk_id),
            "citationIndex": citation.citation_index,
            "excerpt": citation.excerpt,
        }
        passage = deps.seen_passages.get(citation.chunk_id)
        if passage is not None:
            payload.update(
                {
                    "ticker": passage.ticker,
                    "form": passage.form,
                    "fiscalYear": passage.fiscal_year,
                    "page": passage.page,
                    "section": passage.section,
                },
            )
        payloads.append(payload)
    return payloads


def _citation_rows(answer: GroundedAnswer) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": citation.chunk_id,
            "citation_index": citation.citation_index,
            "excerpt": citation.excerpt,
        }
        for citation in answer.citations
    ]


async def run_turn(
    user: CurrentUser,
    thread_id: uuid.UUID,
    messages: list[dict],
) -> AsyncIterator[str]:
    """Run the document agent, stream a grounded reply, persist on success."""
    await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    await asyncio.to_thread(chats.ensure_user, user.id, user.email)

    user_text = extract_latest_user_text(messages)
    deps = DocumentAgentDeps(
        user_id=user.id,
        thread_id=thread_id,
        retriever=DocumentRetriever(),
    )

    try:
        turn = await run_agent(user_text, deps)
        validate_grounded_answer(turn.answer, deps.seen_ids)
    except GroundingError as exc:
        log.warning("grounding_failed", error=str(exc), thread_id=str(thread_id))
        yield format_error(str(exc))
        return
    except (AgentRunError, ModelAPIError, UnexpectedModelBehavior) as exc:
        log.exception("agent_run_failed", error=str(exc), thread_id=str(thread_id))
        yield format_error("The assistant failed to complete this turn.")
        return

    citation_parts = _citation_stream_payloads(turn.answer, deps)
    async for frame in iter_grounded_stream(turn.answer.answer, citation_parts):
        yield frame

    stored = await asyncio.to_thread(
        chats.append_messages,
        thread_id,
        [
            {"role": "user", "message": user_message_for_storage(messages)},
            {
                "role": "assistant",
                "message": assistant_message_for_storage(
                    turn.answer.answer,
                    usage=turn.usage,
                    citations=[{"type": "data-citation", **part} for part in citation_parts],
                ),
            },
        ],
    )
    assistant_id = uuid.UUID(stored[1]["id"])
    await asyncio.to_thread(chats.insert_citations, assistant_id, _citation_rows(turn.answer))

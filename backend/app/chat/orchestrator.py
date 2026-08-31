"""Coordinates one chat turn: agent, grounding, stream, persist."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from openai import APIError
from pydantic_ai.exceptions import AgentRunError, ModelAPIError, UnexpectedModelBehavior

from app.assistant.agent import LOOKING_THROUGH_FILINGS, run_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.grounding import GroundingError, grounding_user_answer, validate_grounded_answer
from app.assistant.outputs import AgentTurnResult, GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.messages import (
    assistant_message_for_storage,
    extract_latest_user_text,
    user_message_for_storage,
)
from app.chat.streaming import (
    format_done,
    format_error,
    format_start_step,
    format_status_part,
    format_stream_start,
    iter_grounded_stream,
)
from app.chat.titles import DEFAULT_THREAD_TITLE, generate_thread_title
from app.database import chats
from app.retrieval.retriever import DocumentRetriever

log = structlog.get_logger(__name__)

AGENT_FAILURES = (AgentRunError, ModelAPIError, UnexpectedModelBehavior, APIError)

ASSISTANT_UNAVAILABLE = "The assistant couldn't complete this answer. Try again."
UNEXPECTED_TURN_ERROR = "Something went wrong. Try again."


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
                    "companyName": passage.company_name,
                    "form": passage.form,
                    "fiscalYear": passage.fiscal_year,
                    "filingDate": passage.filing_date.isoformat(),
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


async def _run_agent_then_close_queue(
    user_text: str,
    deps: DocumentAgentDeps,
    status_queue: asyncio.Queue[str | None],
) -> AgentTurnResult:
    try:
        return await run_agent(user_text, deps)
    finally:
        await status_queue.put(None)


async def run_turn(
    user: CurrentUser,
    thread_id: uuid.UUID,
    messages: list[dict],
    *,
    thread: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Stream search status while the agent runs, then a grounded reply."""
    if thread is None:
        thread = await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    await asyncio.to_thread(chats.ensure_user, user.id, user.email)

    yield format_stream_start()
    yield format_start_step()
    yield format_status_part(LOOKING_THROUGH_FILINGS)

    user_text = extract_latest_user_text(messages)
    status_queue: asyncio.Queue[str | None] = asyncio.Queue()
    deps = DocumentAgentDeps(
        user_id=user.id,
        thread_id=thread_id,
        retriever=DocumentRetriever(),
        status_queue=status_queue,
    )
    agent_task = asyncio.create_task(_run_agent_then_close_queue(user_text, deps, status_queue))

    try:
        while True:
            label = await status_queue.get()
            if label is None:
                break
            yield format_status_part(label)
        turn = await agent_task
    except AGENT_FAILURES:
        log.exception("agent_run_failed", thread_id=str(thread_id))
        yield format_error(ASSISTANT_UNAVAILABLE)
        yield format_done()
        return
    except Exception:
        log.exception("turn_failed", thread_id=str(thread_id))
        yield format_error(UNEXPECTED_TURN_ERROR)
        yield format_done()
        return

    try:
        validate_grounded_answer(turn.answer, deps.seen_ids)
    except GroundingError as exc:
        log.warning(
            "grounding_failed",
            code=exc.code,
            error=str(exc),
            thread_id=str(thread_id),
        )
        canned = grounding_user_answer(exc)
        async for frame in iter_grounded_stream(canned, [], include_envelope=False):
            yield frame
        await _persist_turn(
            thread,
            thread_id,
            messages,
            user_text,
            canned,
            citation_parts=[],
            citation_rows=None,
            usage=None,
        )
        return

    citation_parts = _citation_stream_payloads(turn.answer, deps)
    async for frame in iter_grounded_stream(
        turn.answer.answer,
        citation_parts,
        include_envelope=False,
    ):
        yield frame
    await _persist_turn(
        thread,
        thread_id,
        messages,
        user_text,
        turn.answer.answer,
        citation_parts=citation_parts,
        citation_rows=_citation_rows(turn.answer),
        usage=turn.usage,
    )


async def _persist_turn(
    thread: dict[str, Any],
    thread_id: uuid.UUID,
    messages: list[dict],
    user_text: str,
    answer_text: str,
    *,
    citation_parts: list[dict[str, Any]],
    citation_rows: list[dict[str, Any]] | None,
    usage: dict[str, int] | None,
) -> None:
    stored = await asyncio.to_thread(
        chats.append_messages,
        thread_id,
        [
            {"role": "user", "message": user_message_for_storage(messages)},
            {
                "role": "assistant",
                "message": assistant_message_for_storage(
                    answer_text,
                    usage=usage,
                    citations=(
                        [{"type": "data-citation", "data": part} for part in citation_parts]
                        if citation_parts
                        else None
                    ),
                ),
            },
        ],
    )
    if citation_rows is not None:
        assistant_id = uuid.UUID(stored[1]["id"])
        await asyncio.to_thread(chats.insert_citations, assistant_id, citation_rows)
    await _title_if_new(thread, thread_id, user_text, answer_text)


async def _title_if_new(
    thread: dict[str, Any],
    thread_id: uuid.UUID,
    user_text: str,
    assistant_text: str,
) -> None:
    if thread.get("title") != DEFAULT_THREAD_TITLE:
        return
    try:
        title = await asyncio.to_thread(generate_thread_title, user_text, assistant_text)
        await asyncio.to_thread(chats.update_thread_title, thread_id, title)
    except Exception:
        log.exception("thread_title_failed", thread_id=str(thread_id))

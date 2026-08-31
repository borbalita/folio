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
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.messages import (
    assistant_message_for_storage,
    extract_latest_user_text,
    user_message_for_storage,
)
from app.chat.streaming import (
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

WRITING_THE_ANSWER = "Writing the answer"
_STATUS_POLL_SECONDS = 0.15


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


async def _flush_status(queue: asyncio.Queue[str]) -> AsyncIterator[str]:
    while True:
        try:
            label = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        yield format_status_part(label)


async def run_turn(
    user: CurrentUser,
    thread_id: uuid.UUID,
    messages: list[dict],
) -> AsyncIterator[str]:
    """Run the document agent, stream a grounded reply, persist on success or grounding failure."""
    thread = await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    await asyncio.to_thread(chats.ensure_user, user.id, user.email)

    user_text = extract_latest_user_text(messages)
    status_queue: asyncio.Queue[str] = asyncio.Queue()
    deps = DocumentAgentDeps(
        user_id=user.id,
        thread_id=thread_id,
        retriever=DocumentRetriever(),
        status_queue=status_queue,
    )

    yield format_stream_start()
    yield format_start_step()
    yield format_status_part(LOOKING_THROUGH_FILINGS)

    agent_task = asyncio.create_task(run_agent(user_text, deps))
    while not agent_task.done():
        try:
            label = await asyncio.wait_for(status_queue.get(), timeout=_STATUS_POLL_SECONDS)
            yield format_status_part(label)
        except TimeoutError:
            pass
    async for frame in _flush_status(status_queue):
        yield frame

    try:
        turn = await agent_task
        validate_grounded_answer(turn.answer, deps.seen_ids)
    except GroundingError as exc:
        log.warning(
            "grounding_failed",
            code=exc.code,
            error=str(exc),
            thread_id=str(thread_id),
        )
        canned = grounding_user_answer(exc)
        yield format_status_part(WRITING_THE_ANSWER)
        async for frame in iter_grounded_stream(canned, [], include_envelope=False):
            yield frame
        await asyncio.to_thread(
            chats.append_messages,
            thread_id,
            [
                {"role": "user", "message": user_message_for_storage(messages)},
                {
                    "role": "assistant",
                    "message": assistant_message_for_storage(canned),
                },
            ],
        )
        await _title_if_new(thread, thread_id, user_text, canned)
        return
    except (AgentRunError, ModelAPIError, UnexpectedModelBehavior, APIError) as exc:
        log.exception("agent_run_failed", error=str(exc), thread_id=str(thread_id))
        yield format_error("The assistant failed to complete this turn.")
        return

    yield format_status_part(WRITING_THE_ANSWER)
    citation_parts = _citation_stream_payloads(turn.answer, deps)
    async for frame in iter_grounded_stream(turn.answer.answer, citation_parts, include_envelope=False):
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
                    citations=[{"type": "data-citation", "data": part} for part in citation_parts],
                ),
            },
        ],
    )
    assistant_id = uuid.UUID(stored[1]["id"])
    await asyncio.to_thread(chats.insert_citations, assistant_id, _citation_rows(turn.answer))
    await _title_if_new(thread, thread_id, user_text, turn.answer.answer)


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

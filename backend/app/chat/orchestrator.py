"""Coordinates one chat turn: agent, grounding, stream, persist."""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import structlog
from langfuse import get_client, propagate_attributes
from openai import APIError
from pydantic_ai.exceptions import AgentRunError, ModelAPIError, UnexpectedModelBehavior

from app.assistant.agent import LOOKING_THROUGH_FILINGS, run_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import AgentTurnResult
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
from app.email_assistant.agent import run_email_agent
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailTurnResult
from app.email_assistant.tools.mail import SEARCHING_MAIL
from app.grounding import DocumentGrounder, EmailGrounder, Grounder, GroundingError
from app.retrieval.documents.retriever import DocumentRetriever
from app.retrieval.email.retriever import EmailRetriever
from app.retrieval.news.retriever import NewsPassage, NewsRetriever

log = structlog.get_logger(__name__)

AGENT_FAILURES = (AgentRunError, ModelAPIError, UnexpectedModelBehavior, APIError)

ASSISTANT_UNAVAILABLE = "The assistant couldn't complete this answer. Try again."
UNEXPECTED_TURN_ERROR = "Something went wrong. Try again."

Deps = DocumentAgentDeps | EmailAgentDeps
TurnResult = AgentTurnResult | EmailTurnResult


class _ChatAgent(ABC):
    """What differs between the document and email turns. The turn loop is shared."""

    name: ClassVar[str]
    status_label: ClassVar[str]
    grounder: ClassVar[Grounder]

    @abstractmethod
    def new_deps(
        self,
        user: CurrentUser,
        thread_id: uuid.UUID,
        status_queue: asyncio.Queue[str | None],
    ) -> Deps: ...

    @abstractmethod
    async def run(self, user_text: str, deps: Deps) -> TurnResult: ...

    @abstractmethod
    def passage_fields(self, passage: Any) -> dict[str, Any]: ...

    @abstractmethod
    def citation_target(self, chunk_id: uuid.UUID, passage: Any) -> dict[str, Any]: ...

    @abstractmethod
    def save_citations(
        self, message_id: uuid.UUID, rows: list[dict[str, Any]]
    ) -> None: ...

    def citation_payloads(self, result: TurnResult, deps: Deps) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for citation in result.answer.citations:
            payload: dict[str, Any] = {
                "chunkId": str(citation.chunk_id),
                "citationIndex": citation.citation_index,
                "excerpt": citation.excerpt,
            }
            passage = deps.seen_passages.get(citation.chunk_id)
            if passage is not None:
                payload.update(self.passage_fields(passage))
            payloads.append(payload)
        return payloads

    def citation_rows(self, result: TurnResult, deps: Deps) -> list[dict[str, Any]]:
        return [
            {
                **self.citation_target(
                    citation.chunk_id, deps.seen_passages.get(citation.chunk_id)
                ),
                "citation_index": citation.citation_index,
                "excerpt": citation.excerpt,
            }
            for citation in result.answer.citations
        ]


class _DocumentChatAgent(_ChatAgent):
    name = "documents"
    status_label = LOOKING_THROUGH_FILINGS
    grounder = DocumentGrounder()

    def new_deps(
        self,
        user: CurrentUser,
        thread_id: uuid.UUID,
        status_queue: asyncio.Queue[str | None],
    ) -> DocumentAgentDeps:
        return DocumentAgentDeps(
            user_id=user.id,
            thread_id=thread_id,
            retriever=DocumentRetriever(),
            status_queue=status_queue,
        )

    async def run(self, user_text: str, deps: Deps) -> TurnResult:
        return await run_agent(user_text, deps)

    def passage_fields(self, passage: Any) -> dict[str, Any]:
        return {
            "ticker": passage.ticker,
            "companyName": passage.company_name,
            "form": passage.form,
            "fiscalYear": passage.fiscal_year,
            "filingDate": passage.filing_date.isoformat(),
            "page": passage.page,
            "section": passage.section,
        }

    def citation_target(self, chunk_id: uuid.UUID, passage: Any) -> dict[str, Any]:
        return {"chunk_id": chunk_id}

    def save_citations(self, message_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
        chats.insert_citations(message_id, rows)


class _EmailChatAgent(_ChatAgent):
    name = "email"
    status_label = SEARCHING_MAIL
    grounder = EmailGrounder()

    def new_deps(
        self,
        user: CurrentUser,
        thread_id: uuid.UUID,
        status_queue: asyncio.Queue[str | None],
    ) -> EmailAgentDeps:
        return EmailAgentDeps(
            user_id=user.id,
            thread_id=thread_id,
            retriever=EmailRetriever(),
            news=NewsRetriever(),
            status_queue=status_queue,
        )

    async def run(self, user_text: str, deps: Deps) -> TurnResult:
        return await run_email_agent(user_text, deps)

    def passage_fields(self, passage: Any) -> dict[str, Any]:
        if isinstance(passage, NewsPassage):
            return {
                "title": passage.title,
                "source": passage.source,
                "date": passage.edition_date.isoformat(),
                "url": passage.url,
            }
        return {
            "from": passage.from_address,
            "subject": passage.subject,
            "date": passage.sent_at.date().isoformat(),
            "mailbox": passage.mailbox_name,
        }

    def citation_target(self, chunk_id: uuid.UUID, passage: Any) -> dict[str, Any]:
        if isinstance(passage, NewsPassage):
            return {"email_chunk_id": None, "news_item_id": chunk_id}
        return {"email_chunk_id": chunk_id, "news_item_id": None}

    def save_citations(self, message_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
        chats.insert_email_citations(message_id, rows)


_AGENTS: dict[str, _ChatAgent] = {
    agent.name: agent for agent in (_DocumentChatAgent(), _EmailChatAgent())
}


async def _run_then_close_queue(
    agent: _ChatAgent,
    user_text: str,
    deps: Deps,
    status_queue: asyncio.Queue[str | None],
) -> TurnResult:
    try:
        return await agent.run(user_text, deps)
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
    agent = _AGENTS[thread.get("agent", "documents")]

    yield format_stream_start()
    yield format_start_step()
    yield format_status_part(agent.status_label)

    user_text = extract_latest_user_text(messages)
    log_context = {"agent": agent.name, "thread_id": str(thread_id)}
    langfuse = get_client()
    with (
        langfuse.start_as_current_observation(
            as_type="span",
            name="generate-chat-response",
            input=user_text,
        ) as turn_span,
        propagate_attributes(
            user_id=str(user.id),
            session_id=str(thread_id),
            trace_name="generate-chat-response",
            tags=["chat", agent.name],
        ),
    ):
        status_queue: asyncio.Queue[str | None] = asyncio.Queue()
        deps = agent.new_deps(user, thread_id, status_queue)
        agent_task = asyncio.create_task(
            _run_then_close_queue(agent, user_text, deps, status_queue)
        )

        try:
            while True:
                label = await status_queue.get()
                if label is None:
                    break
                yield format_status_part(label)
            result = await agent_task
        except AGENT_FAILURES:
            log.exception("agent_run_failed", **log_context)
            turn_span.update(
                output=ASSISTANT_UNAVAILABLE,
                level="ERROR",
                status_message="agent_run_failed",
            )
            yield format_error(ASSISTANT_UNAVAILABLE)
            yield format_done()
            return
        except Exception:
            log.exception("turn_failed", **log_context)
            turn_span.update(
                output=UNEXPECTED_TURN_ERROR,
                level="ERROR",
                status_message="turn_failed",
            )
            yield format_error(UNEXPECTED_TURN_ERROR)
            yield format_done()
            return

        try:
            agent.grounder.validate(result.answer, deps.seen_ids)
        except GroundingError as exc:
            log.warning(
                "grounding_failed", code=exc.code, error=str(exc), **log_context
            )
            canned = agent.grounder.user_answer(exc)
            turn_span.update(
                output=canned,
                level="WARNING",
                status_message=exc.code,
                metadata={"grounding_failure_code": exc.code},
            )
            async for frame in iter_grounded_stream(canned, [], include_envelope=False):
                yield frame
            await _persist_turn(
                agent,
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

        citation_parts = agent.citation_payloads(result, deps)
        turn_span.update(
            output=result.answer.answer,
            metadata={
                "citation_count": len(result.answer.citations),
                "insufficient_evidence": result.answer.insufficient_evidence,
                "retrieved_chunk_count": len(deps.seen_ids),
            },
        )
        async for frame in iter_grounded_stream(
            result.answer.answer,
            citation_parts,
            include_envelope=False,
        ):
            yield frame
        await _persist_turn(
            agent,
            thread,
            thread_id,
            messages,
            user_text,
            result.answer.answer,
            citation_parts=citation_parts,
            citation_rows=agent.citation_rows(result, deps),
            usage=result.usage,
        )


async def _persist_turn(
    agent: _ChatAgent,
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
                        [
                            {"type": "data-citation", "data": part}
                            for part in citation_parts
                        ]
                        if citation_parts
                        else None
                    ),
                ),
            },
        ],
    )
    if citation_rows is not None:
        assistant_id = uuid.UUID(stored[1]["id"])
        await asyncio.to_thread(agent.save_citations, assistant_id, citation_rows)
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
        title = await asyncio.to_thread(
            generate_thread_title, user_text, assistant_text
        )
        await asyncio.to_thread(chats.update_thread_title, thread_id, title)
    except Exception:
        log.exception("thread_title_failed", thread_id=str(thread_id))

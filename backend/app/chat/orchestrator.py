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
from app.database import chats, mailboxes
from app.email_assistant.agent import run_email_agent
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailTurnResult
from app.email_assistant.tools.mail import SEARCHING_MAIL
from app.finance_assistant.agent import run_finance_agent
from app.finance_assistant.deps import FinanceAgentDeps
from app.finance_assistant.outputs import FinanceTurnResult
from app.finance_assistant.tools import LOOKING
from app.grounding import (
    DocumentGrounder,
    EmailGrounder,
    Grounder,
    GroundingError,
    NewsGrounder,
)
from app.news_assistant.agent import run_news_agent
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.outputs import NewsTurnResult
from app.news_assistant.tools import READING_NEWSLETTERS
from app.retrieval.documents.retriever import DocumentRetriever
from app.retrieval.email.retriever import EmailRetriever
from app.retrieval.news.retriever import NewsPassage, NewsRetriever

log = structlog.get_logger(__name__)

AGENT_FAILURES = (AgentRunError, ModelAPIError, UnexpectedModelBehavior, APIError)

ASSISTANT_UNAVAILABLE = "The assistant couldn't complete this answer. Try again."
UNEXPECTED_TURN_ERROR = "Something went wrong. Try again."

Deps = DocumentAgentDeps | EmailAgentDeps | FinanceAgentDeps | NewsAgentDeps
TurnResult = AgentTurnResult | EmailTurnResult | FinanceTurnResult | NewsTurnResult


class _ChatAgent(ABC):
    """What differs between agents' turns. The turn loop is shared."""

    name: ClassVar[str]
    status_label: ClassVar[str]

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
    def validate(self, result: TurnResult, deps: Deps) -> None:
        """Raise GroundingError when the answer is not supported by this turn."""

    @abstractmethod
    def user_answer(self, exc: GroundingError) -> str: ...

    @abstractmethod
    def data_parts(self, result: TurnResult, deps: Deps) -> list[dict[str, Any]]:
        """AI SDK data parts streamed after the text and stored with the message."""

    @abstractmethod
    def turn_metadata(self, result: TurnResult, deps: Deps) -> dict[str, Any]: ...

    def citation_rows(
        self, result: TurnResult, deps: Deps
    ) -> list[dict[str, Any]] | None:
        return None

    def save_citations(self, message_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
        return None


class _CitingChatAgent(_ChatAgent):
    """Agents whose answers cite retrieved passages, checked by a grounder."""

    grounder: ClassVar[Grounder]

    @abstractmethod
    def passage_fields(self, passage: Any) -> dict[str, Any]: ...

    @abstractmethod
    def citation_target(self, chunk_id: uuid.UUID, passage: Any) -> dict[str, Any]: ...

    def validate(self, result: TurnResult, deps: Deps) -> None:
        self.grounder.validate(result.answer, deps.seen_ids)

    def user_answer(self, exc: GroundingError) -> str:
        return self.grounder.user_answer(exc)

    def turn_metadata(self, result: TurnResult, deps: Deps) -> dict[str, Any]:
        return {
            "citation_count": len(result.answer.citations),
            "insufficient_evidence": result.answer.insufficient_evidence,
            "retrieved_chunk_count": len(deps.seen_ids),
        }

    def data_parts(self, result: TurnResult, deps: Deps) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for citation in result.answer.citations:
            payload: dict[str, Any] = {
                "chunkId": str(citation.chunk_id),
                "citationIndex": citation.citation_index,
                "excerpt": citation.excerpt,
            }
            passage = deps.seen_passages.get(citation.chunk_id)
            if passage is not None:
                payload.update(self.passage_fields(passage))
            parts.append({"type": "data-citation", "data": payload})
        return parts

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


class _DocumentChatAgent(_CitingChatAgent):
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


class _EmailChatAgent(_CitingChatAgent):
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


class _NewsChatAgent(_CitingChatAgent):
    """Cites newsletter items; they are stored as news citations in email_citations."""

    name = "news"
    status_label = READING_NEWSLETTERS
    grounder = NewsGrounder()

    def new_deps(
        self,
        user: CurrentUser,
        thread_id: uuid.UUID,
        status_queue: asyncio.Queue[str | None],
    ) -> NewsAgentDeps:
        return NewsAgentDeps(
            user_id=user.id,
            thread_id=thread_id,
            news=NewsRetriever(),
            status_queue=status_queue,
        )

    async def run(self, user_text: str, deps: Deps) -> TurnResult:
        return await run_news_agent(user_text, deps)

    def passage_fields(self, passage: Any) -> dict[str, Any]:
        return {
            "title": passage.title,
            "source": passage.source,
            "date": passage.edition_date.isoformat(),
            "url": passage.url,
        }

    def citation_target(self, chunk_id: uuid.UUID, passage: Any) -> dict[str, Any]:
        return {"email_chunk_id": None, "news_item_id": chunk_id}

    def save_citations(self, message_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
        chats.insert_email_citations(message_id, rows)


class _FinanceChatAgent(_ChatAgent):
    """Answers carry cards, not citations; card ids must come from this turn's tools."""

    name = "finance"
    status_label = LOOKING

    def new_deps(
        self,
        user: CurrentUser,
        thread_id: uuid.UUID,
        status_queue: asyncio.Queue[str | None],
    ) -> FinanceAgentDeps:
        return FinanceAgentDeps(
            user_id=user.id,
            thread_id=thread_id,
            mailbox_ids=[],
            status_queue=status_queue,
        )

    async def run(self, user_text: str, deps: Deps) -> TurnResult:
        deps.mailbox_ids = await asyncio.to_thread(
            mailboxes.active_mailbox_ids, deps.user_id
        )
        return await run_finance_agent(user_text, deps)

    def validate(self, result: TurnResult, deps: Deps) -> None:
        # Unknown card ids are dropped in data_parts rather than failing the answer.
        return None

    def user_answer(self, exc: GroundingError) -> str:
        return ASSISTANT_UNAVAILABLE

    def data_parts(self, result: TurnResult, deps: Deps) -> list[dict[str, Any]]:
        seen = {"invoices": deps.seen_invoice_ids, "payments": deps.seen_draft_ids}
        parts: list[dict[str, Any]] = []
        for card in result.answer.cards:
            kept = [card_id for card_id in card.ids if card_id in seen[card.kind]]
            if len(kept) < len(card.ids):
                # Ids, not content, but still not needed to see that the model made one up.
                log.warning(
                    "finance_card_id_dropped",
                    kind=card.kind,
                    count=len(card.ids) - len(kept),
                    thread_id=str(deps.thread_id),
                )
            if kept:
                parts.append(
                    {
                        "type": "data-finance-card",
                        "data": {"kind": card.kind, "ids": [str(i) for i in kept]},
                    }
                )
        return parts

    def turn_metadata(self, result: TurnResult, deps: Deps) -> dict[str, Any]:
        return {"card_count": len(result.answer.cards)}


_AGENTS: dict[str, _ChatAgent] = {
    agent.name: agent
    for agent in (
        _DocumentChatAgent(),
        _EmailChatAgent(),
        _NewsChatAgent(),
        _FinanceChatAgent(),
    )
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
                level="ERROR",
                status_message="agent_run_failed",
            )
            yield format_error(ASSISTANT_UNAVAILABLE)
            yield format_done()
            return
        except Exception:
            log.exception("turn_failed", **log_context)
            turn_span.update(
                level="ERROR",
                status_message="turn_failed",
            )
            yield format_error(UNEXPECTED_TURN_ERROR)
            yield format_done()
            return

        try:
            agent.validate(result, deps)
        except GroundingError as exc:
            log.warning(
                "grounding_failed", code=exc.code, error=str(exc), **log_context
            )
            canned = agent.user_answer(exc)
            turn_span.update(
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
                data_parts=[],
                citation_rows=None,
                usage=None,
            )
            return

        data_parts = agent.data_parts(result, deps)
        turn_span.update(metadata=agent.turn_metadata(result, deps))
        async for frame in iter_grounded_stream(
            result.answer.answer,
            data_parts,
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
            data_parts=data_parts,
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
    data_parts: list[dict[str, Any]],
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
                    parts=data_parts,
                ),
            },
        ],
    )
    if citation_rows:
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

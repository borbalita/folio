from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.database import mailboxes
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer, EmailCitationRef
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailPassage, EmailRetriever
from app.retrieval.news.retriever import NewsRetriever
from evals.agent_run import run_agent
from evals.modes.e2e import RecordingRetriever
from evals.scoring import answer_scores, search_recall

USER = UUID("00000000-0000-0000-0000-000000000001")
MAILBOX = UUID("00000000-0000-0000-0000-000000000010")


def _chunk(n: int) -> UUID:
    return UUID(int=n)


OWNERS = {_chunk(1): "e01", _chunk(2): "e01", _chunk(3): "e02", _chunk(4): "e03"}


def _passage(chunk_id: UUID) -> EmailPassage:
    return EmailPassage(
        chunk_id=chunk_id,
        email_id=uuid.uuid4(),
        text="The workshop moved to 28 September.",
        from_address="elin@archive.example",
        subject="Workshop moved",
        sent_at=datetime(2026, 9, 10, tzinfo=UTC),
        mailbox_name="Yahoo",
        fusion_score=0.0,
    )


# Recall across searches


def test_search_recall_counts_an_email_found_by_any_call() -> None:
    calls = [["e05", "e07"], ["e01", "e05"]]

    assert search_recall(calls, ["e01", "e02"]) == 0.5


def test_search_recall_counts_an_email_once_across_calls() -> None:
    calls = [["e01"], ["e01", "e02"], ["e02"]]

    assert search_recall(calls, ["e01", "e02"]) == 1.0


def test_search_recall_without_searches_is_zero() -> None:
    assert search_recall([], ["e01"]) == 0.0


def test_search_recall_does_not_apply_without_expected_emails() -> None:
    assert search_recall([["e01"]], []) is None


# Recorded searches


def test_recording_retriever_keeps_each_search_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    returned = {
        "workshop": [_passage(_chunk(3)), _passage(_chunk(1)), _passage(_chunk(2))],
        "archive": [_passage(_chunk(4))],
    }
    monkeypatch.setattr(
        EmailRetriever,
        "search",
        lambda self, query, *, filters, session=None, question=None: returned[query],
    )
    retriever = RecordingRetriever(OWNERS, rerank=False)

    retriever.search(
        "workshop",
        filters=EmailSearchFilters(
            user_id=USER,
            mailbox_ids=[MAILBOX],
            since=date(2026, 9, 1),
            sender="elin@archive.example",
        ),
    )
    retriever.search(
        "archive", filters=EmailSearchFilters(user_id=USER, mailbox_ids=[MAILBOX])
    )

    first, second = retriever.calls
    assert (first.query, first.since, first.sender) == (
        "workshop",
        date(2026, 9, 1),
        "elin@archive.example",
    )
    assert first.email_keys == ["e02", "e01"]
    assert (second.query, second.since, second.email_keys) == ("archive", None, ["e03"])


def test_agent_run_records_every_search_it_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda _user: [MAILBOX])
    returned = {
        "workshop": [_passage(_chunk(3))],
        "workshop moved": [_passage(_chunk(1))],
    }
    monkeypatch.setattr(
        EmailRetriever,
        "search",
        lambda self, query, *, filters, session=None, question=None: returned[query],
    )

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        searches = sum(
            isinstance(part, ToolReturnPart)
            for message in messages
            for part in message.parts
        )
        if searches < 2:
            query = ["workshop", "workshop moved"][searches]
            args = {"query": query, "sender": "elin"} if searches else {"query": query}
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="search_emails",
                        args=args,
                        tool_call_id=f"s{searches}",
                    )
                ]
            )
        answer = {
            "answer": "28 September.",
            "citations": [{"chunk_id": str(_chunk(1)), "citation_index": 1}],
        }
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name, args=answer, tool_call_id="o1"
                )
            ]
        )

    retriever = RecordingRetriever(OWNERS, rerank=False)
    deps = EmailAgentDeps(
        user_id=USER, thread_id=uuid.uuid4(), retriever=retriever, news=NewsRetriever()
    )

    record = asyncio.run(
        run_agent(
            "When is the workshop now?", date(2026, 10, 1), deps, FunctionModel(respond)
        )
    )

    assert [s.args for s in record.steps] == [
        {"query": "workshop"},
        {"query": "workshop moved", "sender": "elin"},
    ]
    assert [(c.query, c.sender, c.email_keys) for c in retriever.calls] == [
        ("workshop", None, ["e02"]),
        ("workshop moved", "elin", ["e01"]),
    ]
    assert search_recall([c.email_keys for c in retriever.calls], ["e01"]) == 1.0


# Grounding when the case planned no evidence


def test_grounding_is_checked_once_the_model_saw_evidence() -> None:
    scores = answer_scores(
        EmailAnswer(
            answer="It is on 28 September.",
            citations=[EmailCitationRef(chunk_id=_chunk(9), citation_index=1)],
        ),
        answerable=False,
        expected_chunk_ids=set(),
        distractor_chunk_ids=set(),
        seen_ids={_chunk(4)},
    )

    assert scores.refusal_outcome == "missing_refusal"
    assert (scores.grounding_pass, scores.grounding_error) == (0.0, "unknown_chunk")

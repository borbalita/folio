from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import run_turn
from app.database import chats, mailboxes
from app.email_assistant.outputs import EmailAnswer, EmailCitationRef
from app.email_assistant.tools.mail import execute_search_emails
from app.grounding import UNKNOWN_CHUNK, EmailGrounder, GroundingError
from app.retrieval.email.retriever import EmailPassage
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

SEEN = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
UNKNOWN = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
USER = CurrentUser(id=TEST_USER_ID, email="test@example.com")


class _Usage:
    requests = 1
    input_tokens = 2
    output_tokens = 3
    tool_calls = 1


class _Agent:
    def __init__(self, citations: list[EmailCitationRef]) -> None:
        self.prompt = ""
        self.citations = citations

    async def run(self, prompt: str, deps: object) -> SimpleNamespace:
        self.prompt = prompt
        execute_search_emails(deps, "rent")  # type: ignore[arg-type]
        return SimpleNamespace(
            output=EmailAnswer(
                answer="Rent is due Friday.",
                citations=self.citations,
            ),
            usage=_Usage(),
        )


def _patch(monkeypatch: pytest.MonkeyPatch, agent: _Agent) -> list[dict]:
    stored: list[dict] = []
    monkeypatch.setattr("app.email_assistant.agent.get_agent", lambda: agent)
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])
    monkeypatch.setattr(
        "app.retrieval.email.retriever.EmailRetriever.search",
        lambda self, query, *, filters, session=None: [
            EmailPassage(
                chunk_id=SEEN,
                email_id=uuid.uuid4(),
                text="Rent is due Friday.",
                from_address="landlord@example.com",
                subject="September rent",
                sent_at=datetime(2026, 9, 4, tzinfo=UTC),
                mailbox_name="Yahoo",
                fusion_score=1.0,
            )
        ],
    )
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chats,
        "append_messages",
        lambda thread_id, messages: [
            {"id": str(uuid.uuid4())},
            {"id": str(uuid.uuid4())},
        ],
    )
    monkeypatch.setattr(
        chats,
        "insert_email_citations",
        lambda message_id, citations: stored.extend(citations),
    )
    return stored


def _run(
    monkeypatch: pytest.MonkeyPatch, citations: list[EmailCitationRef]
) -> tuple[str, list[dict], _Agent]:
    agent = _Agent(citations)
    stored = _patch(monkeypatch, agent)

    async def _collect() -> str:
        frames: list[str] = []
        async for frame in run_turn(
            USER,
            TEST_THREAD_ID,
            [{"role": "user", "content": "When is rent due?"}],
            thread={"id": str(TEST_THREAD_ID), "title": "Mail", "agent": "email"},
        ):
            frames.append(frame)
        return "".join(frames)

    return asyncio.run(_collect()), stored, agent


def test_turn_stores_a_chunk_the_tool_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, stored, agent = _run(
        monkeypatch,
        [EmailCitationRef(chunk_id=SEEN, citation_index=1, excerpt="Rent")],
    )

    assert [row["email_chunk_id"] for row in stored] == [SEEN]
    assert all(row["news_item_id"] is None for row in stored)
    assert "Europe/Berlin" in agent.prompt
    assert "September rent" in body


def test_turn_refuses_an_unknown_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    body, stored, agent = _run(
        monkeypatch,
        [
            EmailCitationRef(chunk_id=SEEN, citation_index=1, excerpt="Rent"),
            EmailCitationRef(chunk_id=UNKNOWN, citation_index=2, excerpt="other"),
        ],
    )
    canned = EmailGrounder().user_answer(GroundingError(UNKNOWN_CHUNK, "internal"))

    assert stored == []
    assert _streamed_text(body) == canned
    assert "Europe/Berlin" in agent.prompt


def _streamed_text(body: str) -> str:
    deltas = [
        json.loads(line[len("data: ") :])["delta"]
        for line in body.splitlines()
        if line.startswith("data: {") and '"text-delta"' in line
    ]
    return "".join(deltas)

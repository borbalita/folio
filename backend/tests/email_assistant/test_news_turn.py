from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import date
from types import SimpleNamespace

import pytest

from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import run_turn
from app.database import chats, mailboxes
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer, EmailCitationRef
from app.email_assistant.tools.news import execute_list_big_news, execute_search_news
from app.grounding import UNKNOWN_CHUNK, EmailGrounder, GroundingError
from app.retrieval.news.retriever import BigStory, NewsPassage
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

TLDR_ITEM = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ALPHA_ITEM = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
STORY = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
USER = CurrentUser(id=TEST_USER_ID, email="test@example.com")


def _item(item_id: uuid.UUID, source: str) -> NewsPassage:
    return NewsPassage(
        item_id=item_id,
        story_id=STORY,
        source=source,
        edition_date=date(2026, 9, 22),
        title="Robot hands learn to fold laundry",
        blurb="A new policy folds shirts at home.",
        url="https://example.com/robots",
        score=0.5,
    )


class _Usage:
    requests = 1
    input_tokens = 2
    output_tokens = 3
    tool_calls = 1


class _Agent:
    def __init__(
        self,
        tool: Callable[[EmailAgentDeps], str],
        citations: list[EmailCitationRef],
    ) -> None:
        self.tool = tool
        self.citations = citations

    async def run(self, prompt: str, deps: EmailAgentDeps) -> SimpleNamespace:
        self.tool(deps)
        return SimpleNamespace(
            output=EmailAnswer(
                answer="Robot hands learned to fold laundry.",
                citations=self.citations,
            ),
            usage=_Usage(),
        )


def _patch(monkeypatch: pytest.MonkeyPatch, agent: _Agent) -> list[dict]:
    stored: list[dict] = []
    monkeypatch.setattr("app.email_assistant.agent.get_agent", lambda: agent)
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])
    monkeypatch.setattr(
        "app.retrieval.news.retriever.NewsRetriever.search",
        lambda self, query, *, filters, session=None: [_item(TLDR_ITEM, "tldr")],
    )
    monkeypatch.setattr(
        "app.retrieval.news.retriever.NewsRetriever.big_stories",
        lambda self, *, filters, session=None: [
            BigStory(
                story_id=STORY,
                first_seen=date(2026, 9, 21),
                last_seen=date(2026, 9, 22),
                items=[_item(ALPHA_ITEM, "alpha_signal"), _item(TLDR_ITEM, "tldr")],
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
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    tool: Callable[[EmailAgentDeps], str],
    citations: list[EmailCitationRef],
) -> tuple[str, list[dict]]:
    stored = _patch(monkeypatch, _Agent(tool, citations))

    async def _collect() -> str:
        frames: list[str] = []
        async for frame in run_turn(
            USER,
            TEST_THREAD_ID,
            [{"role": "user", "content": question}],
            thread={"id": str(TEST_THREAD_ID), "title": "News", "agent": "email"},
        ):
            frames.append(frame)
        return "".join(frames)

    return asyncio.run(_collect()), stored


def _cite(item_id: uuid.UUID, index: int) -> EmailCitationRef:
    return EmailCitationRef(
        chunk_id=item_id, citation_index=index, excerpt="Robot hands"
    )


def test_big_news_last_week_cites_news_items(monkeypatch: pytest.MonkeyPatch) -> None:
    body, stored = _run(
        monkeypatch,
        "What was the big news last week?",
        lambda deps: execute_list_big_news(
            deps, since=date(2026, 9, 21), until=date(2026, 9, 27)
        ),
        [_cite(ALPHA_ITEM, 1), _cite(TLDR_ITEM, 2)],
    )

    assert [row["news_item_id"] for row in stored] == [ALPHA_ITEM, TLDR_ITEM]
    assert all(row["email_chunk_id"] is None for row in stored)
    assert "Robot hands learn to fold laundry" in body
    assert "https://example.com/robots" in body


def test_news_about_robots_last_month_cites_news_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, stored = _run(
        monkeypatch,
        "Any news about robots last month?",
        lambda deps: execute_search_news(
            deps, "robots", since=date(2026, 8, 1), until=date(2026, 8, 31)
        ),
        [_cite(TLDR_ITEM, 1)],
    )

    assert [row["news_item_id"] for row in stored] == [TLDR_ITEM]
    assert stored[0]["email_chunk_id"] is None
    assert "https://example.com/robots" in body


def test_citing_the_story_id_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    body, stored = _run(
        monkeypatch,
        "What was the big news last week?",
        lambda deps: execute_list_big_news(deps),
        [_cite(STORY, 1)],
    )
    canned = EmailGrounder().user_answer(GroundingError(UNKNOWN_CHUNK, "internal"))

    assert stored == []
    assert _streamed_text(body) == canned


def _streamed_text(body: str) -> str:
    deltas = [
        json.loads(line[len("data: ") :])["delta"]
        for line in body.splitlines()
        if line.startswith("data: {") and '"text-delta"' in line
    ]
    return "".join(deltas)

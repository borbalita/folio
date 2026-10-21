from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import run_turn
from app.database import chats, mailboxes
from app.grounding import UNKNOWN_CHUNK, GroundingError, NewsGrounder
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.outputs import NewsAnswer, NewsCitationRef
from app.news_assistant.tools import execute_list_big_news
from app.retrieval.news.retriever import NewsPassage, Story
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
        edition_date=date(2026, 10, 20),
        title="Lab ships a new model",
        blurb="It reasons better.",
        url="https://example.com/model",
        score=0.0,
    )


class _Usage:
    requests = 1
    input_tokens = 2
    output_tokens = 3
    tool_calls = 1


class _Agent:
    def __init__(self, citations: list[NewsCitationRef]) -> None:
        self.citations = citations
        self.prompts: list[str] = []

    async def run(self, prompt: str, deps: NewsAgentDeps) -> SimpleNamespace:
        self.prompts.append(prompt)
        execute_list_big_news(deps)
        return SimpleNamespace(
            output=NewsAnswer(
                answer="A lab shipped a new model.", citations=self.citations
            ),
            usage=_Usage(),
        )


def _run(monkeypatch: pytest.MonkeyPatch, agent: _Agent) -> tuple[str, list[dict]]:
    stored: list[dict] = []
    monkeypatch.setattr("app.news_assistant.agent.get_agent", lambda: agent)
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [uuid.uuid4()])
    monkeypatch.setattr(
        "app.retrieval.news.retriever.NewsRetriever.stories",
        lambda self, *, filters, limit, session=None: [
            Story(
                story_id=STORY,
                first_seen=date(2026, 10, 20),
                last_seen=date(2026, 10, 20),
                is_big=True,
                sources=["alpha_signal", "tldr"],
                item_count=2,
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
        chats, "insert_email_citations", lambda message_id, rows: stored.extend(rows)
    )

    async def _collect() -> str:
        frames = [
            frame
            async for frame in run_turn(
                USER,
                TEST_THREAD_ID,
                [{"role": "user", "content": "What were the big stories this week?"}],
                thread={"id": str(TEST_THREAD_ID), "title": "News", "agent": "news"},
            )
        ]
        return "".join(frames)

    return asyncio.run(_collect()), stored


def _cite(item_id: uuid.UUID, index: int) -> NewsCitationRef:
    return NewsCitationRef(chunk_id=item_id, citation_index=index, excerpt="new model")


def _streamed_text(body: str) -> str:
    return "".join(
        json.loads(line[len("data: ") :])["delta"]
        for line in body.splitlines()
        if line.startswith("data: {") and '"text-delta"' in line
    )


def test_big_news_cites_the_returned_items_as_news(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _Agent([_cite(ALPHA_ITEM, 1), _cite(TLDR_ITEM, 2)])

    body, stored = _run(monkeypatch, agent)

    assert [row["news_item_id"] for row in stored] == [ALPHA_ITEM, TLDR_ITEM]
    assert all(row["email_chunk_id"] is None for row in stored)
    assert "https://example.com/model" in body
    assert agent.prompts[0].startswith("Today is ")


def test_citing_the_story_id_is_refused_with_news_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, stored = _run(monkeypatch, _Agent([_cite(STORY, 1)]))
    canned = NewsGrounder().user_answer(GroundingError(UNKNOWN_CHUNK, "internal"))

    assert stored == []
    assert _streamed_text(body) == canned
    assert "newsletter" in canned


class _EmptyAgent:
    async def run(self, prompt: str, deps: NewsAgentDeps) -> SimpleNamespace:
        return SimpleNamespace(
            output=NewsAnswer(
                answer="There were no big stories since Saturday.",
                citations=[],
                insufficient_evidence=True,
            ),
            usage=_Usage(),
        )


def test_an_empty_period_answer_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    body, stored = _run(monkeypatch, _EmptyAgent())  # type: ignore[arg-type]

    assert stored == []
    assert _streamed_text(body) == "There were no big stories since Saturday."

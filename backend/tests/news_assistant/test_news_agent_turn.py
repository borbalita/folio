from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelResponse
from pydantic_ai.messages import NativeToolCallPart, NativeToolReturnPart

from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import run_turn
from app.database import chats, mailboxes
from app.grounding import UNKNOWN_CHUNK, GroundingError, NewsGrounder
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.outputs import NewsAnswer, NewsCitationRef, WebCitationRef
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
            new_messages=list,
        )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    agent: _Agent,
    stored_messages: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    stored: list[dict] = []
    monkeypatch.setattr(
        "app.news_assistant.agent.get_agent", lambda *, web_search: agent
    )
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [uuid.uuid4()])
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
        lambda thread_id, messages: (
            stored_messages.extend(messages) if stored_messages is not None else None,
            [{"id": str(uuid.uuid4())}, {"id": str(uuid.uuid4())}],
        )[1],
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
            new_messages=list,
        )


def test_an_empty_period_answer_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    body, stored = _run(monkeypatch, _EmptyAgent())  # type: ignore[arg-type]

    assert stored == []
    assert _streamed_text(body) == "There were no big stories since Saturday."


WEB_URL = "https://example.com/report?sid=1"


class _WebAgent:
    """Reads the newsletters, searches the web, and cites both plus a made-up page."""

    def __init__(self, *, answer: str = "From the newsletter and the web.") -> None:
        self.answer = answer

    async def run(self, prompt: str, deps: NewsAgentDeps) -> SimpleNamespace:
        execute_list_big_news(deps)
        return SimpleNamespace(
            output=NewsAnswer(
                answer=self.answer,
                citations=[_cite(ALPHA_ITEM, 1)],
                web_citations=[
                    WebCitationRef(
                        url=WEB_URL,
                        title="The report",
                        citation_index=2,
                        excerpt="from the page",
                    ),
                    WebCitationRef(
                        url="https://made.up/page",
                        title="Made up",
                        citation_index=3,
                        excerpt="nothing",
                    ),
                ],
            ),
            usage=_Usage(),
            new_messages=lambda: [
                ModelResponse(
                    parts=[
                        NativeToolCallPart(
                            "web_search", {"type": "search", "queries": ["q"]}
                        ),
                        NativeToolReturnPart(
                            "web_search",
                            {
                                "status": "completed",
                                "sources": [
                                    {"type": "url", "url": "https://example.com/report"}
                                ],
                            },
                        ),
                    ]
                )
            ],
        )


def _citation_parts(message: dict) -> list[dict]:
    return [part["data"] for part in message["parts"] if part["type"] == "data-citation"]


def test_web_and_item_citations_are_stored_and_read_back_with_their_own_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[dict] = []

    body, rows = _run(monkeypatch, _WebAgent(), messages)

    item, web = _citation_parts(messages[1]["message"])
    assert "kind" not in item
    assert item["chunkId"] == str(ALPHA_ITEM)
    assert item["title"] == "Lab ships a new model"
    assert item["source"] == "alpha_signal"
    assert web == {
        "chunkId": WEB_URL,
        "citationIndex": 2,
        "excerpt": "from the page",
        "kind": "web",
        "title": "The report",
        "url": WEB_URL,
    }
    assert '"kind": "web"' in body or '"kind":"web"' in body

    assert rows == [
        {
            "email_chunk_id": None,
            "news_item_id": ALPHA_ITEM,
            "citation_index": 1,
            "excerpt": "new model",
        },
        {
            "email_chunk_id": None,
            "news_item_id": None,
            "web_url": WEB_URL,
            "web_title": "The report",
            "citation_index": 2,
            "excerpt": "from the page",
        },
    ]


def test_a_made_up_web_citation_is_removed_and_the_answer_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[dict] = []

    body, _rows = _run(monkeypatch, _WebAgent(), messages)

    assert _streamed_text(body) == "From the newsletter and the web."
    assert "made.up" not in body
    assert "made.up" not in json.dumps(messages)


def test_markers_never_reach_the_stream_or_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[dict] = []
    agent = _WebAgent(
        answer="It shipped. \ue200cite\ue202turn593528view1\ue201 citeturn1search2turn3view4"
    )

    body, _rows = _run(monkeypatch, agent, messages)

    assert _streamed_text(body) == "It shipped."
    stored = json.dumps(messages, ensure_ascii=False)
    assert "turn593528" not in stored and "\ue200" not in stored
    assert "citeturn" not in stored


def test_a_stored_thread_with_only_item_citations_keeps_its_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item citations written from now on match what stored threads already hold."""
    messages: list[dict] = []

    _body, _rows = _run(monkeypatch, _Agent([_cite(ALPHA_ITEM, 1)]), messages)

    assert _citation_parts(messages[1]["message"]) == [
        {
            "chunkId": str(ALPHA_ITEM),
            "citationIndex": 1,
            "excerpt": "new model",
            "title": "Lab ships a new model",
            "source": "alpha_signal",
            "date": "2026-10-20",
            "url": "https://example.com/model",
        }
    ]

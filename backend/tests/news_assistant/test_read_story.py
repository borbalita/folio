from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.database import mailboxes, news_story
from app.grounding import UNKNOWN_CHUNK, GroundingError, NewsGrounder
from app.news_assistant.agent import get_agent, run_news_agent
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.tools import execute_read_story
from app.retrieval.news.retriever import NewsRetriever
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID
from tests.news_fakes import FakeNewsDb, news_row

MINE = uuid.UUID(int=10)
OTHERS = uuid.UUID(int=11)
EMAIL = uuid.UUID(int=20)


def _deps(story_items: list[tuple[uuid.UUID, int]] | None = None) -> NewsAgentDeps:
    return NewsAgentDeps(
        user_id=TEST_USER_ID,
        thread_id=TEST_THREAD_ID,
        news=NewsRetriever(),
        story_items=story_items or [],
        story_title="Lab ships a new model" if story_items else None,
    )


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeNewsDb:
    fake = FakeNewsDb([])
    monkeypatch.setattr(news_story, "get_session", fake.session)
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda user_id: [MINE])
    return fake


def test_read_story_returns_the_edition_with_the_story_named(db: FakeNewsDb) -> None:
    row = news_row(mailbox_id=MINE, body="Details the blurb leaves out.")
    db.rows.append(row)
    deps = _deps()

    text = execute_read_story(deps, row.id)

    assert row.title in text and "Details the blurb leaves out." in text
    assert str(row.id) in text
    assert deps.seen_ids == {row.id}


def test_read_story_for_an_item_outside_the_mailboxes_returns_nothing_from_that_mail(
    db: FakeNewsDb,
) -> None:
    theirs = news_row(mailbox_id=OTHERS, body="Another user's private text.", title="Their story")
    db.rows.append(theirs)
    deps = _deps()

    text = execute_read_story(deps, theirs.id)

    assert "private text" not in text and "Their story" not in text
    assert deps.seen_ids == set()


def _scripted(calls: list[str], cite: uuid.UUID, prompts: list[str]) -> FunctionModel:
    """Reads the story once, then answers citing `cite`."""

    def respond(messages, info: AgentInfo) -> ModelResponse:
        first = messages[0].parts
        prompts.append(next(p.content for p in first if isinstance(p, UserPromptPart)))
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("read_story", {"item_id": calls[0]})]
            )
        answer = {
            "answer": "The lab shipped it.",
            "citations": [
                {"chunk_id": str(cite), "citation_index": 1, "excerpt": "new model"}
            ],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])

    return FunctionModel(respond)


def _turn(deps: NewsAgentDeps, model: FunctionModel):
    async def go():
        with get_agent().override(model=model):
            return await run_news_agent("Explain this story", deps)

    return asyncio.run(go())


def test_citing_an_item_read_with_read_story_is_grounded(db: FakeNewsDb) -> None:
    row = news_row(mailbox_id=MINE)
    db.rows.append(row)
    deps = _deps()

    result = _turn(deps, _scripted([str(row.id)], row.id, []))

    NewsGrounder().validate(result.answer, deps.seen_ids)


def test_citing_an_item_no_tool_returned_is_refused(db: FakeNewsDb) -> None:
    row = news_row(mailbox_id=MINE)
    db.rows.append(row)
    deps = _deps()

    result = _turn(deps, _scripted([str(row.id)], uuid.uuid4(), []))

    with pytest.raises(GroundingError) as raised:
        NewsGrounder().validate(result.answer, deps.seen_ids)
    assert raised.value.code == UNKNOWN_CHUNK


def test_citing_an_item_that_read_story_refused_is_refused(db: FakeNewsDb) -> None:
    theirs = news_row(mailbox_id=OTHERS)
    db.rows.append(theirs)
    deps = _deps()

    result = _turn(deps, _scripted([str(theirs.id)], theirs.id, []))

    with pytest.raises(GroundingError):
        NewsGrounder().validate(result.answer, deps.seen_ids)


def test_the_prompt_names_the_story_and_its_current_item_ids_after_re_embedding(
    db: FakeNewsDb,
) -> None:
    # The same newsletter item (email, position) gets a new id when its email is re-embedded.
    before = news_row(mailbox_id=MINE, email_id=EMAIL, position=4)
    db.rows.append(before)
    first_prompts: list[str] = []
    _turn(_deps([(EMAIL, 4)]), _scripted([str(before.id)], before.id, first_prompts))

    db.rows[:] = [news_row(mailbox_id=MINE, email_id=EMAIL, position=4)]
    after = db.rows[0]
    second_prompts: list[str] = []
    _turn(_deps([(EMAIL, 4)]), _scripted([str(after.id)], after.id, second_prompts))

    assert "Lab ships a new model" in first_prompts[0]
    assert str(before.id) in first_prompts[0]
    assert str(after.id) in second_prompts[0]
    assert str(before.id) not in second_prompts[0]
    assert second_prompts[0].endswith("Explain this story")


def test_a_thread_without_a_story_gets_the_plain_prompt(db: FakeNewsDb) -> None:
    row = news_row(mailbox_id=MINE)
    db.rows.append(row)
    prompts: list[str] = []

    _turn(_deps(), _scripted([str(row.id)], row.id, prompts))

    assert "one story" not in prompts[0]
    assert db.statements and len(db.statements) == 1  # only read_story queried


def test_story_items_of_another_users_mail_name_nothing(db: FakeNewsDb) -> None:
    theirs = news_row(mailbox_id=OTHERS, email_id=EMAIL, position=4, title="Their story")
    db.rows.append(theirs)
    prompts: list[str] = []

    _turn(_deps([(EMAIL, 4)]), _scripted([str(theirs.id)], theirs.id, prompts))

    assert str(theirs.id) not in prompts[0]
    assert "Their story" not in prompts[0]

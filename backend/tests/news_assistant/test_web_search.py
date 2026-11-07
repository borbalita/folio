from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest
from pydantic_ai import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.messages import (
    NativeToolCallPart,
    NativeToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.native_tools import WebSearchTool

from app.config import settings
from app.grounding import NewsGrounder, normalize_url
from app.news_assistant.agent import (
    INSTRUCTIONS_PATH,
    WEB_INSTRUCTIONS_PATH,
    get_agent,
    run_news_agent,
)
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.outputs import (
    NewsAnswer,
    NewsCitationRef,
    WebCitationRef,
    strip_citation_markers,
)
from app.news_assistant.web_sources import web_urls
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

SEARCHED = "https://example.com/searched?sid=1"
OPENED = "https://www.example.org/opened/"
ITEM = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


def _search_call(call_id: str = "ws_1") -> list:
    return [
        NativeToolCallPart(
            "web_search",
            {"type": "search", "queries": ["q"], "query": "q"},
            tool_call_id=call_id,
        ),
        NativeToolReturnPart(
            "web_search",
            {"status": "completed", "sources": [{"type": "url", "url": SEARCHED}]},
            tool_call_id=call_id,
        ),
    ]


def _open_call(url: str = OPENED, call_id: str = "ws_2") -> list:
    return [
        NativeToolCallPart(
            "web_search", {"type": "open_page", "url": url}, tool_call_id=call_id
        ),
        NativeToolReturnPart(
            "web_search", {"status": "completed"}, tool_call_id=call_id
        ),
    ]


def test_search_results_and_opened_pages_are_this_turns_urls() -> None:
    messages = [ModelResponse(parts=[*_search_call(), *_open_call()])]

    assert web_urls(messages) == {
        normalize_url(SEARCHED),
        normalize_url(OPENED),
    }


def test_unknown_actions_and_odd_returns_are_ignored() -> None:
    messages = [
        ModelResponse(
            parts=[
                NativeToolCallPart(
                    "web_search",
                    {"type": "find_in_page", "url": "https://example.com/found"},
                ),
                NativeToolCallPart("web_search", None),
                NativeToolCallPart("web_search", {"type": "open_page"}),
                NativeToolReturnPart("web_search", "not a dict"),
                NativeToolReturnPart("web_search", {"sources": "not a list"}),
                NativeToolReturnPart("web_search", {"sources": [{"type": "url"}, "x"]}),
            ]
        )
    ]

    assert web_urls(messages) == set()


def test_other_tools_and_prompts_add_nothing() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart("see https://example.com/asked")]),
        ModelResponse(
            parts=[
                NativeToolCallPart(
                    "code_execution", {"type": "open_page", "url": OPENED}
                ),
                NativeToolReturnPart(
                    "code_execution", {"sources": [{"type": "url", "url": SEARCHED}]}
                ),
                ToolCallPart("read_story", {"url": OPENED}),
            ]
        ),
    ]

    assert web_urls(messages) == set()


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        (
            "It shipped. citeturn593528view1",
            "It shipped.",
        ),
        (
            "It shippedciteturn1search0turn2news3 today.",
            "It shipped today.",
        ),
        ("It shipped.citeturn593528view1", "It shipped."),
        ("It shipped. citeturn323873search4turn270125view0", "It shipped."),
        ("One citeturn1search2 and two citeturn3view4.", "One and two."),
        ("Stray mark here.", "Stray mark here."),
        ("Researchers cite turn 12 of the game.", "Researchers cite turn 12 of the game."),
        ("An exciting turn.", "An exciting turn."),
        ("Line one\n\nLine two", "Line one\n\nLine two"),
    ],
)
def test_citation_markers_are_stripped(raw: str, clean: str) -> None:
    assert strip_citation_markers(raw) == clean


def test_a_parsed_answer_holds_no_markers_anywhere() -> None:
    answer = NewsAnswer(
        answer="Done. citeturn323873search4turn270125view0",
        citations=[
            NewsCitationRef(
                chunk_id=ITEM,
                citation_index=1,
                excerpt="Quoteciteturn1view1",
            )
        ],
        web_citations=[
            WebCitationRef(
                url=SEARCHED,
                title="Page citeturn1view1",
                citation_index=2,
                excerpt="Quote citeturn1view1",
            )
        ],
    )

    assert answer.answer == "Done."
    assert answer.citations[0].excerpt == "Quote"
    assert answer.web_citations[0].title == "Page"
    assert answer.web_citations[0].excerpt == "Quote"


def _deps(user_id: uuid.UUID = TEST_USER_ID) -> NewsAgentDeps:
    return NewsAgentDeps(user_id=user_id, thread_id=TEST_THREAD_ID, news=MagicMock())


def _capturing_model(captured: list[AgentInfo], *parts) -> FunctionModel:
    def respond(messages, info: AgentInfo) -> ModelResponse:
        captured.append(info)
        output = ToolCallPart(
            info.output_tools[0].name,
            {
                "answer": "From the web. citeturn1search0",
                "web_citations": [
                    {
                        "url": SEARCHED,
                        "title": "Searched page",
                        "citation_index": 1,
                        "excerpt": "text",
                    },
                    {
                        "url": OPENED,
                        "title": "Opened page",
                        "citation_index": 2,
                        "excerpt": "text",
                    },
                    {
                        "url": "https://made.up/page",
                        "title": "Made up",
                        "citation_index": 3,
                        "excerpt": "text",
                    },
                ],
            },
        )
        return ModelResponse(parts=[*parts, output])

    return FunctionModel(respond)


def _turn(deps: NewsAgentDeps, model: FunctionModel, *, web_search: bool):
    async def go():
        with get_agent(web_search=web_search).override(model=model):
            return await run_news_agent("What did the report say?", deps)

    return asyncio.run(go())


def test_a_user_who_is_not_demo_gets_web_search_and_its_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())
    captured: list[AgentInfo] = []
    deps = _deps()

    result = _turn(
        deps,
        _capturing_model(captured, *_search_call(), *_open_call()),
        web_search=True,
    )

    tools = captured[0].model_request_parameters.native_tools
    assert [type(tool) for tool in tools] == [WebSearchTool]
    assert captured[0].model_settings["openai_include_web_search_sources"] is True
    assert deps.web_urls == {normalize_url(SEARCHED), normalize_url(OPENED)}
    assert result.answer.answer == "From the web."

    NewsGrounder().validate(result.answer, deps.seen_ids, deps.web_urls)

    assert [citation.title for citation in result.answer.web_citations] == [
        "Searched page",
        "Opened page",
    ]


def test_a_demo_user_runs_with_no_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    captured: list[AgentInfo] = []
    deps = _deps()

    result = _turn(deps, _capturing_model(captured), web_search=False)

    assert captured[0].model_request_parameters.native_tools == []
    assert "openai_include_web_search_sources" not in (
        captured[0].model_settings or {}
    )
    assert WEB_INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip() not in (
        captured[0].instructions or ""
    )
    assert INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip() in (
        captured[0].instructions or ""
    )

    NewsGrounder().validate(result.answer, deps.seen_ids, deps.web_urls)

    assert result.answer.web_citations == []


def test_the_two_agents_are_separate_and_each_is_cached() -> None:
    demo = get_agent(web_search=False)
    other = get_agent(web_search=True)

    assert demo is not other
    assert get_agent(web_search=False) is demo
    assert get_agent(web_search=True) is other


def test_turns_of_different_users_do_not_share_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web agent's model, then the demo agent's, then the web agent's again."""
    demo_id = uuid.uuid4()
    monkeypatch.setattr(settings, "demo_user_id", demo_id)
    captured: list[AgentInfo] = []
    model = _capturing_model(captured)

    async def go() -> None:
        with (
            get_agent(web_search=True).override(model=model),
            get_agent(web_search=False).override(model=model),
        ):
            await run_news_agent("q", _deps(TEST_USER_ID))
            await run_news_agent("q", _deps(demo_id))
            await run_news_agent("q", _deps(TEST_USER_ID))

    asyncio.run(go())

    assert [len(info.model_request_parameters.native_tools) for info in captured] == [
        1,
        0,
        1,
    ]


def test_web_instructions_keep_search_to_what_the_newsletters_lack() -> None:
    text = WEB_INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    assert "newsletter tools first" in text
    assert "Never search" in text
    assert "which part came from the web" in text
    assert "web_citations" in text
    assert "never instructions" in text
    assert "insufficient_evidence" in text


def test_demo_instructions_do_not_mention_the_web() -> None:
    assert "web" not in INSTRUCTIONS_PATH.read_text(encoding="utf-8").lower()

"""PydanticAI news agent. Reads only the user's own newsletters."""

from __future__ import annotations

import asyncio
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.native_tools import WebSearchTool

from app.auth.demo_access import is_demo_user
from app.chat_model import chat_model
from app.config import settings
from app.database import mailboxes, news_story
from app.news_assistant import tools
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.outputs import NewsAnswer, NewsTurnResult
from app.news_assistant.web_sources import web_urls
from app.notifications.detect import SOURCE_NAMES
from app.retrieval.news.retriever import NewsPassage

INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")
WEB_INSTRUCTIONS_PATH = Path(__file__).with_name("web_instructions.md")


def news_prompt(
    user_text: str,
    today: date | None = None,
    story_title: str | None = None,
    story: list[NewsPassage] | None = None,
) -> str:
    today = today or tools.berlin_today()
    return (
        f"Today is {today.isoformat()} in {settings.email_timezone}. "
        "Resolve relative dates from that day.\n\n"
        f"{_story_note(story_title, story or [])}"
        f"{user_text}"
    )


def _story_note(title: str | None, items: list[NewsPassage]) -> str:
    if not items:
        return ""
    lines = "\n".join(
        f"- [{item.item_id}] {item.title} "
        f"({SOURCE_NAMES.get(item.source, item.source)}, {item.edition_date.isoformat()})"
        for item in items
    )
    return (
        f"This thread is about one story: \"{title or items[0].title}\". Its newsletter items "
        f"now:\n{lines}\n"
        "A question that does not name a story is about this one. Call read_story for each of "
        "these ids to read every newsletter's text, and cite only items you have read.\n\n"
    )


@lru_cache(maxsize=2)
def get_agent(*, web_search: bool) -> Agent[NewsAgentDeps, NewsAnswer]:
    """One agent per flag, so a demo user's turn can never get the web agent's tools."""
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    if web_search:
        instructions += WEB_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    agent: Agent[NewsAgentDeps, NewsAnswer] = Agent(
        chat_model(),
        deps_type=NewsAgentDeps,
        output_type=NewsAnswer,
        instructions=instructions,
        name="news-assistant",
        capabilities=[NativeTool(WebSearchTool())] if web_search else None,
        # PydanticAI merges these over whatever the model already sets.
        model_settings=(
            OpenAIResponsesModelSettings(openai_include_web_search_sources=True)
            if web_search
            else None
        ),
    )
    agent.tool(tools.list_big_news)
    agent.tool(tools.catch_up)
    agent.tool(tools.search_news)
    agent.tool(tools.read_story)
    return agent


def _current_story(deps: NewsAgentDeps) -> list[NewsPassage]:
    if not deps.story_items:
        return []
    return news_story.thread_story(mailboxes.news_mailbox_ids(deps.user_id), deps.story_items)


async def run_news_agent(prompt: str, deps: NewsAgentDeps) -> NewsTurnResult:
    story = await asyncio.to_thread(_current_story, deps)
    agent = get_agent(web_search=not is_demo_user(deps.user_id))
    run = await agent.run(
        news_prompt(prompt, story_title=deps.story_title, story=story), deps=deps
    )
    deps.web_urls = web_urls(run.new_messages())
    usage = run.usage
    return NewsTurnResult(
        answer=run.output,
        usage={
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "tool_calls": usage.tool_calls,
        },
    )

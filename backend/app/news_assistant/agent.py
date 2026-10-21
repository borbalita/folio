"""PydanticAI news agent. Reads only the user's own newsletters."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent

from app.chat_model import chat_model
from app.config import settings
from app.news_assistant import tools
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.outputs import NewsAnswer, NewsTurnResult

INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")


def news_prompt(user_text: str, today: date | None = None) -> str:
    today = today or tools.berlin_today()
    return (
        f"Today is {today.isoformat()} in {settings.email_timezone}. "
        "Resolve relative dates from that day.\n\n"
        f"{user_text}"
    )


@lru_cache(maxsize=1)
def get_agent() -> Agent[NewsAgentDeps, NewsAnswer]:
    agent: Agent[NewsAgentDeps, NewsAnswer] = Agent(
        chat_model(),
        deps_type=NewsAgentDeps,
        output_type=NewsAnswer,
        instructions=INSTRUCTIONS_PATH.read_text(encoding="utf-8"),
        name="news-assistant",
    )
    agent.tool(tools.list_big_news)
    agent.tool(tools.catch_up)
    agent.tool(tools.search_news)
    return agent


async def run_news_agent(prompt: str, deps: NewsAgentDeps) -> NewsTurnResult:
    run = await get_agent().run(news_prompt(prompt), deps=deps)
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

"""PydanticAI email agent. Search is scoped to the user's active mailboxes."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer, EmailTurnResult
from app.email_assistant.tools import mail, news

INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")


def _chat_model() -> OpenAIChatModel:
    return OpenAIChatModel(
        settings.openai_chat_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )


def email_prompt(user_text: str) -> str:
    today = datetime.now(ZoneInfo(settings.email_timezone)).date().isoformat()
    return (
        f"Today is {today} in {settings.email_timezone}. "
        "Resolve relative dates from that day.\n\n"
        f"{user_text}"
    )


@lru_cache(maxsize=1)
def get_agent() -> Agent[EmailAgentDeps, EmailAnswer]:
    agent: Agent[EmailAgentDeps, EmailAnswer] = Agent(
        _chat_model(),
        deps_type=EmailAgentDeps,
        output_type=EmailAnswer,
        instructions=INSTRUCTIONS_PATH.read_text(encoding="utf-8"),
        name="email-assistant",
    )
    agent.tool(mail.search_emails)
    agent.tool(news.search_news)
    agent.tool(news.list_big_news)
    return agent


async def run_email_agent(prompt: str, deps: EmailAgentDeps) -> EmailTurnResult:
    run = await get_agent().run(email_prompt(prompt), deps=deps)
    usage = run.usage
    return EmailTurnResult(
        answer=run.output,
        usage={
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "tool_calls": usage.tool_calls,
        },
    )

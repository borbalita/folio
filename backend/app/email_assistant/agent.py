"""PydanticAI email agent. Search is scoped to the user's active mailboxes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer, EmailTurnResult
from app.email_assistant.tools import execute_search_emails, parse_label

INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")

SEARCHING_MAIL = "Searching your mail"


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
    agent.tool(search_emails)
    return agent


async def search_emails(
    ctx: RunContext[EmailAgentDeps],
    query: str,
    since: str | None = None,
    until: str | None = None,
    label: str | None = None,
    sender: str | None = None,
    mailbox: str | None = None,
) -> str:
    """Search the user's mail. Optional since, until (YYYY-MM-DD), label, sender, and mailbox."""
    if ctx.deps.status_queue is not None:
        await ctx.deps.status_queue.put(SEARCHING_MAIL)
    known_label = parse_label(label)
    if label and known_label is None:
        return "Unknown label. Use needs_reply, promotional, newsletter, invoice, other, or ai_newsletter."
    try:
        since_day = _parse_day(since)
        until_day = _parse_day(until)
    except ValueError:
        return "since and until must be YYYY-MM-DD."
    return await asyncio.to_thread(
        execute_search_emails,
        ctx.deps,
        query,
        since=since_day,
        until=until_day,
        label=known_label,
        sender=sender,
        mailbox=mailbox,
    )


def _parse_day(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value.strip())


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

"""PydanticAI document agent with bounded retrieval tools."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import AgentTurnResult, GroundedAnswer
from app.assistant.tools import (
    execute_read_chunk,
    execute_read_surrounding_chunks,
    execute_search_filings,
)
from app.config import settings

INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")


def _chat_model() -> OpenAIChatModel:
    return OpenAIChatModel(
        settings.openai_chat_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )


@lru_cache(maxsize=1)
def get_agent() -> Agent[DocumentAgentDeps, GroundedAnswer]:
    agent: Agent[DocumentAgentDeps, GroundedAnswer] = Agent(
        _chat_model(),
        deps_type=DocumentAgentDeps,
        output_type=GroundedAnswer,
        instructions=INSTRUCTIONS_PATH.read_text(encoding="utf-8"),
        name="document-copilot",
    )
    agent.tool(search_filings)
    agent.tool(read_chunk)
    agent.tool(read_surrounding_chunks)
    return agent


async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    ticker: str | None = None,
    fiscal_years: list[int] | None = None,
    form: str | None = None,
) -> str:
    """Search the SEC 10-K corpus. Optional ticker, fiscal_years, and form narrow the filings."""
    return await asyncio.to_thread(
        execute_search_filings,
        ctx.deps,
        query,
        ticker=ticker,
        fiscal_years=fiscal_years,
        form=form,
    )


async def read_chunk(ctx: RunContext[DocumentAgentDeps], chunk_id: UUID) -> str:
    """Read one retrieved chunk by id."""
    return await asyncio.to_thread(execute_read_chunk, ctx.deps, chunk_id)


async def read_surrounding_chunks(ctx: RunContext[DocumentAgentDeps], chunk_id: UUID) -> str:
    """Read neighboring chunks around a chunk id in the same filing."""
    return await asyncio.to_thread(execute_read_surrounding_chunks, ctx.deps, chunk_id)


async def run_agent(prompt: str, deps: DocumentAgentDeps) -> AgentTurnResult:
    agent = get_agent()
    run = await agent.run(prompt, deps=deps)
    usage = run.usage
    return AgentTurnResult(
        answer=run.output,
        usage={
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "tool_calls": usage.tool_calls,
        },
    )

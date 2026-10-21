"""PydanticAI finance agent. Every tool is scoped to the owner's mailboxes or banks."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent

from app.chat_model import chat_model
from app.config import settings
from app.finance_assistant import tools
from app.finance_assistant.deps import FinanceAgentDeps
from app.finance_assistant.outputs import FinanceAnswer, FinanceTurnResult

INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")


def finance_prompt(user_text: str, today: date | None = None) -> str:
    today = today or datetime.now(ZoneInfo(settings.email_timezone)).date()
    return f"Today is {today.isoformat()} in {settings.email_timezone}.\n\n{user_text}"


@lru_cache(maxsize=1)
def get_agent() -> Agent[FinanceAgentDeps, FinanceAnswer]:
    agent: Agent[FinanceAgentDeps, FinanceAnswer] = Agent(
        chat_model(),
        deps_type=FinanceAgentDeps,
        output_type=FinanceAnswer,
        instructions=INSTRUCTIONS_PATH.read_text(encoding="utf-8"),
        name="finance-assistant",
    )
    for tool in (
        tools.list_invoices,
        tools.get_invoice,
        tools.search_transactions,
        tools.list_accounts,
        tools.prepare_payments,
    ):
        agent.tool(tool)
    return agent


async def run_finance_agent(prompt: str, deps: FinanceAgentDeps) -> FinanceTurnResult:
    run = await get_agent().run(finance_prompt(prompt), deps=deps)
    usage = run.usage
    return FinanceTurnResult(
        answer=run.output,
        usage={
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "tool_calls": usage.tool_calls,
        },
    )

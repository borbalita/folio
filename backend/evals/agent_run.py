"""Run the real email agent for one case and keep what it did, step by step."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings
from app.email_assistant.agent import email_prompt, get_agent
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.outputs import EmailAnswer

# PydanticAI's tool for a structured output; it carries the answer, not a search.
OUTPUT_TOOL = "final_result"


class ToolStep(BaseModel):
    tool: str
    args: dict[str, Any] | str | None
    result: str | None
    """What the tool returned to the model; None if the run ended before it returned."""


class AgentRecord(BaseModel):
    answer: EmailAnswer
    steps: list[ToolStep]
    usage: dict[str, int]


def chat_model(name: str) -> Model:
    return OpenAIChatModel(
        name, provider=OpenAIProvider(api_key=settings.openai_api_key)
    )


async def run_agent(
    question: str, today: date, deps: EmailAgentDeps, model: Model
) -> AgentRecord:
    run = await get_agent().run(
        email_prompt(question, today=today), deps=deps, model=model
    )
    usage = run.usage
    return AgentRecord(
        answer=run.output,
        steps=tool_steps(run.all_messages()),
        usage={
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "tool_calls": usage.tool_calls,
        },
    )


def tool_steps(messages: list[ModelMessage]) -> list[ToolStep]:
    """Tool calls in order, each with what it returned. The final-answer tool is left out."""
    returns = {
        part.tool_call_id: part.model_response_str()
        for message in messages
        if not isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    return [
        ToolStep(
            tool=part.tool_name,
            args=part.args,
            result=returns.get(part.tool_call_id),
        )
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name != OUTPUT_TOOL
    ]

"""Short thread titles from the first user question and assistant reply."""

from __future__ import annotations

from functools import lru_cache

import structlog
from openai import APIError
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings

log = structlog.get_logger(__name__)

DEFAULT_THREAD_TITLE = "New chat"
TITLE_MAX_CHARS = 80
ANSWER_PREVIEW_CHARS = 500

_SYSTEM_PROMPT = (
    "Write a 4 to 8 word title for an SEC 10-K research chat. "
    "Name the company or ticker, year if present, and the topic. "
    "No quotation marks, no New chat, no Document Copilot."
)


class ThreadTitle(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_CHARS)


@lru_cache(maxsize=1)
def _title_agent() -> Agent[None, ThreadTitle]:
    return Agent(
        OpenAIChatModel(
            settings.openai_chat_model,
            provider=OpenAIProvider(api_key=settings.openai_api_key),
        ),
        output_type=ThreadTitle,
        instructions=_SYSTEM_PROMPT,
        name="thread-title",
    )


def title_from_question(question: str) -> str:
    collapsed = " ".join(question.split())
    if not collapsed:
        return DEFAULT_THREAD_TITLE
    return _clamp(collapsed)


def _clamp(text: str) -> str:
    if len(text) <= TITLE_MAX_CHARS:
        return text
    return text[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def _normalize_title(raw: str, fallback: str) -> str:
    cleaned = " ".join(raw.replace("\n", " ").split()).strip(" \"'")
    if not cleaned:
        return fallback
    return _clamp(cleaned)


def generate_thread_title(question: str, answer: str) -> str:
    fallback = title_from_question(question)
    preview = " ".join(answer.split())[:ANSWER_PREVIEW_CHARS]
    try:
        result = _title_agent().run_sync(f"Question: {question}\nAnswer: {preview}")
    except (AgentRunError, ModelAPIError, UnexpectedModelBehavior, APIError) as exc:
        log.warning("thread_title_llm_failed", error=str(exc))
        return fallback

    return _normalize_title(result.output.title, fallback)

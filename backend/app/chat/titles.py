"""Short thread titles from the first user question and assistant reply."""

from __future__ import annotations

from functools import lru_cache

import structlog
from openai import APIError, OpenAI
from pydantic import BaseModel, Field

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
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


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
        completion = _client().chat.completions.parse(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {question}\nAnswer: {preview}",
                },
            ],
            response_format=ThreadTitle,
        )
    except APIError as exc:
        log.warning("thread_title_llm_failed", error=str(exc))
        return fallback

    parsed = completion.choices[0].message.parsed
    if parsed is None or not parsed.title.strip():
        return fallback
    return _normalize_title(parsed.title, fallback)

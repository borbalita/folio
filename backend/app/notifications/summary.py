"""One model call per big story: a headline and a plain explanation, read from the newsletters."""

from __future__ import annotations

import uuid
from functools import lru_cache

import structlog
from openai import NOT_GIVEN, OpenAI, OpenAIError
from openai.types.chat import ParsedChatCompletion
from pydantic import BaseModel, Field

from app.config import settings
from app.notifications.detect import (
    SOURCE_NAMES,
    NewsItemFacts,
    news_fallback_text,
    news_message,
)

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "Newsletters covered one story; their full text follows, with the story's titles named as "
    "the focus. Other stories in the same newsletters are not part of it: ignore them. Write a "
    "headline of at most 12 words and an explanation in plain words that lets the reader "
    "understand the story without opening a link: what happened, any technical term explained, "
    "and why it matters. Be as long as that needs and no longer; it is not a briefing. State "
    "facts about the event only from the newsletters. Plain-word definitions and why it "
    "matters may go beyond them. Plain text, no markdown, in English."
)


class NewsSummary(BaseModel):
    headline: str = Field(description="At most 12 words.")
    summary: str = Field(description="A plain explanation, as long as needed to understand it.")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def summary_messages(
    items: list[NewsItemFacts], editions: dict[uuid.UUID, str]
) -> list[dict[str, str]]:
    # Links stay outside the model: they go into the message as they are.
    titles = "\n".join(f"- {item.title}" for item in items)
    # Items of one newsletter share its text, which is sent once.
    sources = {item.email_id: item.source for item in items}
    newsletters = "\n\n".join(
        f"=== {SOURCE_NAMES.get(source, source)} newsletter ===\n{editions[email_id]}"
        for email_id, source in sources.items()
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"The story:\n{titles}\n\n{newsletters}"},
    ]


def request_summary(
    items: list[NewsItemFacts], editions: dict[uuid.UUID, str]
) -> ParsedChatCompletion[NewsSummary]:
    effort = settings.news_extraction_reasoning_effort
    return _client().chat.completions.parse(
        model=settings.news_extraction_model or settings.openai_chat_model,
        messages=summary_messages(items, editions),
        response_format=NewsSummary,
        reasoning_effort=effort if effort is not None else NOT_GIVEN,
    )


def news_text(items: list[NewsItemFacts], editions: dict[uuid.UUID, str]) -> str:
    """The big-news message; a failed call still sends the first headline, its blurb and the links."""
    try:
        parsed = request_summary(items, editions).choices[0].message.parsed
    except (OpenAIError, ValueError) as exc:
        # Any failure (API, content filter, length, unparseable output) falls back: a summary
        # that can't be written must not block this or any other notification.
        log.warning("news_summary_failed", error=type(exc).__name__)
        return news_fallback_text(items)
    if parsed is None:
        log.warning("news_summary_failed", error="no_parsed_output")
        return news_fallback_text(items)
    return news_message(parsed.headline.strip(), parsed.summary.strip(), items)

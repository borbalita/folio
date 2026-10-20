"""One model call per big story: a headline and a short summary of both newsletters."""

from __future__ import annotations

from functools import lru_cache

import structlog
from openai import NOT_GIVEN, OpenAI, OpenAIError
from openai.types.chat import ParsedChatCompletion
from pydantic import BaseModel, Field

from app.config import settings
from app.notifications.detect import NewsItemFacts, news_fallback_text, news_message

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "Two AI newsletters covered the same story. Write a headline of at most 12 words and a "
    "summary of 2 or 3 short sentences that combines what they say. Use only the facts given; "
    "don't add opinions or details. Plain text, no markdown, in English."
)


class NewsSummary(BaseModel):
    headline: str = Field(description="At most 12 words.")
    summary: str = Field(description="2 or 3 short sentences.")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def summary_messages(items: list[NewsItemFacts]) -> list[dict[str, str]]:
    # Titles and blurbs only: the links go into the message as they are, not through the model.
    body = "\n\n".join(f"{item.source}: {item.title}\n{item.blurb}" for item in items)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": body},
    ]


def request_summary(items: list[NewsItemFacts]) -> ParsedChatCompletion[NewsSummary]:
    effort = settings.news_extraction_reasoning_effort
    return _client().chat.completions.parse(
        model=settings.news_extraction_model or settings.openai_chat_model,
        messages=summary_messages(items),
        response_format=NewsSummary,
        reasoning_effort=effort if effort is not None else NOT_GIVEN,
    )


def news_text(items: list[NewsItemFacts]) -> str:
    """The big-news message; a failed call still sends the first headline and the links."""
    try:
        parsed = request_summary(items).choices[0].message.parsed
    except (OpenAIError, ValueError) as exc:
        # Any failure (API, content filter, length, unparseable output) falls back: a summary
        # that can't be written must not block this or any other notification.
        log.warning("news_summary_failed", error=type(exc).__name__)
        return news_fallback_text(items)
    if parsed is None:
        log.warning("news_summary_failed", error="no_parsed_output")
        return news_fallback_text(items)
    return news_message(parsed.headline.strip(), parsed.summary.strip(), items)

"""Extract news items from an AI newsletter. Sponsor blocks are dropped."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import structlog
from openai import NOT_GIVEN, APIError, OpenAI
from openai.types.chat import ParsedChatCompletion
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel, Field

from app.config import settings
from ingest.email.parse import ParsedMessage

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "Extract the news items from this newsletter in the order they appear. "
    "Each item has a title, a one-sentence blurb, and the story url. "
    "Mark sponsor as true for a paid sponsor, an ad, or a 'together with' placement. "
    "Also mark as sponsor the newsletter's own job listings and advertising offers. "
    "Leave those blocks in the list so they stay in order."
)


class ExtractedItem(BaseModel):
    title: str
    blurb: str
    url: str
    sponsor: bool = Field(
        default=False,
        description="True for a paid sponsor, an ad, or a together-with placement.",
    )


class Extraction(BaseModel):
    items: list[ExtractedItem]


Extractor = Callable[[ParsedMessage], list[ExtractedItem] | None]


def edition_date(sent_at: datetime) -> date:
    return sent_at.astimezone(ZoneInfo(settings.email_timezone)).date()


def embed_text(item: ExtractedItem) -> str:
    return f"{item.title}\n{item.blurb}"


def extract_news_items(
    parsed: ParsedMessage, *, extract: Extractor | None = None
) -> list[ExtractedItem]:
    ask = extract or extract_with_model
    try:
        raw = ask(parsed)
    except APIError as exc:
        log.warning("email_news_extract_failed", error=type(exc).__name__)
        return []
    if not raw:
        return []
    return [item for item in raw if not item.sponsor]


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def request_extraction(
    parsed: ParsedMessage,
    *,
    model: str,
    reasoning_effort: ReasoningEffort | None,
) -> ParsedChatCompletion[Extraction]:
    """One extraction call with the production prompt and schema. Evals call this directly."""
    effort = reasoning_effort if reasoning_effort is not None else NOT_GIVEN
    return _client().chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Subject: {parsed.subject}\n\n{parsed.body}",
            },
        ],
        response_format=Extraction,
        reasoning_effort=effort,
    )


def extract_with_model(parsed: ParsedMessage) -> list[ExtractedItem] | None:
    completion = request_extraction(
        parsed,
        model=settings.news_extraction_model or settings.openai_chat_model,
        reasoning_effort=settings.news_extraction_reasoning_effort,
    )
    parsed_items = completion.choices[0].message.parsed
    if parsed_items is None:
        return None
    return parsed_items.items

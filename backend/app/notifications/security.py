"""One model call that marks which newsletter items are security stories worth an alert."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Literal

import structlog
from openai import NOT_GIVEN, OpenAI, OpenAIError
from openai.types.chat import ParsedChatCompletion
from pydantic import BaseModel, Field

from app.config import settings
from app.notifications.detect import SOURCE_NAMES

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "You mark which items of AI newsletters are security stories that deserve an alert.\n"
    "Qualifies: AI as the target, tool or cause of harm (sandbox escapes, malicious AI "
    "tooling, model misuse, critical flaws found by AI); active exploitation; critical flaws "
    "in widely used software; large breaches or hacks.\n"
    "Does not qualify: advice and opinion pieces, security products and partnerships, bug "
    "bounty programmes, routine patches, stories that only mention security.\n"
    "For each item give security true or false. For a security item also give alert: new when "
    "it is a first alert about an incident, update when something materially changed since "
    "the earlier alert (for example a flaw is now under attack, or a patch or a bigger breach "
    "count came out), repeat when it only covers an incident already alerted without "
    "anything material. Compare with the alerts of the last 7 days and with the other items "
    "of this batch: the same incident in several items is one new, then repeats or updates. "
    "Items are listed oldest first. Answer for every item by its index."
)


class ItemVerdict(BaseModel):
    index: int = Field(description="The item's index in the list.")
    security: bool
    alert: Literal["new", "update", "repeat"] | None = Field(
        default=None, description="Only for security items."
    )


class Verdicts(BaseModel):
    items: list[ItemVerdict]


@dataclass(frozen=True)
class Candidate:
    email_id: uuid.UUID
    position: int
    edition_date: date
    source: str
    title: str
    blurb: str


@dataclass(frozen=True)
class Classification:
    email_id: uuid.UUID
    position: int
    security: bool
    alert_status: str | None


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def classification_messages(
    candidates: list[Candidate], recent_alerts: list[str]
) -> list[dict[str, str]]:
    alerts = "\n".join(f"- {headline}" for headline in recent_alerts) or "(none)"
    items = "\n".join(
        f"[{index}] {c.edition_date} {SOURCE_NAMES.get(c.source, c.source)}: {c.title}"
        + (f" — {c.blurb}" if c.blurb else "")
        for index, c in enumerate(candidates)
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Alerts of the last 7 days:\n{alerts}\n\nItems:\n{items}"},
    ]


def request_classification(
    candidates: list[Candidate], recent_alerts: list[str]
) -> ParsedChatCompletion[Verdicts]:
    effort = settings.news_extraction_reasoning_effort
    return _client().chat.completions.parse(
        model=settings.news_extraction_model or settings.openai_chat_model,
        messages=classification_messages(candidates, recent_alerts),
        response_format=Verdicts,
        reasoning_effort=effort if effort is not None else NOT_GIVEN,
    )


def parse(verdicts: Verdicts, candidates: list[Candidate]) -> list[Classification]:
    """One classification per answered item. Unknown or repeated indices are dropped."""
    results: dict[int, Classification] = {}
    for verdict in verdicts.items:
        if not 0 <= verdict.index < len(candidates) or verdict.index in results:
            continue
        candidate = candidates[verdict.index]
        # A status only means something on a security item. A security item with none sends
        # nothing: an alert needs the model to have said it is one.
        status = verdict.alert if verdict.security else None
        results[verdict.index] = Classification(
            candidate.email_id, candidate.position, verdict.security, status
        )
    return [results[index] for index in sorted(results)]


def classify(candidates: list[Candidate], recent_alerts: list[str]) -> list[Classification] | None:
    """The answered items, or None when the call failed. Items the model skipped are absent."""
    try:
        verdicts = request_classification(candidates, recent_alerts).choices[0].message.parsed
    except (OpenAIError, ValueError) as exc:
        # Any failure (API, content filter, length, unparseable output) is retried next run.
        # The type only: the message could echo newsletter text.
        log.warning("news_classification_failed", error=type(exc).__name__)
        return None
    if verdicts is None:
        log.warning("news_classification_failed", error="no_parsed_output")
        return None
    return parse(verdicts, candidates)

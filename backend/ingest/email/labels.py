"""Label a message before it is stored. AI newsletters skip the model."""

from __future__ import annotations

from collections.abc import Callable
from email.utils import parseaddr
from typing import Annotated, Literal

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior
from pydantic_ai.models.typesafe import TypeSafeModel
from pydantic_ai.providers.typesafe import TypeSafeProvider

from app.config import settings
from app.database.models.email.message import EmailLabel, NewsletterSource
from ingest.email.parse import ParsedMessage

log = structlog.get_logger(__name__)

Classifier = Callable[[str], str | None]
BODY_CHARS = 4000
CLASSIFIER_LABELS = (
    EmailLabel.NEEDS_REPLY,
    EmailLabel.PROMOTIONAL,
    EmailLabel.NEWSLETTER,
    EmailLabel.INVOICE,
    EmailLabel.OTHER,
)

# A plain Literal becomes a JSON schema `enum`, and Jev then sees the names with
# no descriptions. A union of single-value literals keeps each option's meaning.
_LabelOption = (
    Annotated[
        Literal["needs_reply"],
        Field(description="A person expects an answer."),
    ]
    | Annotated[
        Literal["promotional"],
        Field(description="Marketing, sales, or a newsletter whose point is to sell."),
    ]
    | Annotated[
        Literal["newsletter"],
        Field(
            description=(
                "An informational mailing that is not an AI digest and not a sales pitch."
            )
        ),
    ]
    | Annotated[
        Literal["invoice"],
        Field(description="A bill or payment request, including a PDF invoice."),
    ]
    | Annotated[
        Literal["other"],
        Field(
            description="Personal or transactional mail with no reply needed, and not a bill."
        ),
    ]
)


class LabelDecision(BaseModel):
    """Choose the one label that fits this email."""

    label: _LabelOption = Field(description="Which label fits this email?")


def newsletter_match(from_address: str) -> NewsletterSource | None:
    _name, address = parseaddr(from_address)
    sender = (address or from_address).strip().lower()
    domain = sender.split("@", 1)[1] if "@" in sender else sender
    mapping = settings.ai_newsletter_domains
    source = mapping.get(sender) or mapping.get(domain)
    if source is None:
        return None
    try:
        return NewsletterSource(source)
    except ValueError:
        log.warning("email_newsletter_source_unknown", sender=sender, source=source)
        return None


def label(
    parsed: ParsedMessage,
    *,
    classifier: Classifier | None = None,
) -> EmailLabel:
    prompt = _classifier_input(parsed)
    ask = classifier or label_with_jev
    for attempt in (1, 2):
        raw = ask(prompt)
        label = _known_label(raw)
        if label is not None:
            return label
        log.warning("email_label_invalid", attempt=attempt, output=raw)
    log.warning("email_label_fallback", message_id=parsed.message_id)
    return EmailLabel.OTHER


def label_message(
    parsed: ParsedMessage,
    *,
    classifier: Classifier | None = None,
) -> tuple[EmailLabel, NewsletterSource | None]:
    source = newsletter_match(parsed.from_address)
    if source is not None:
        return EmailLabel.AI_NEWSLETTER, source
    return label(parsed, classifier=classifier), None


def _classifier_input(parsed: ParsedMessage) -> str:
    names = ", ".join(parsed.attachment_filenames) or "none"
    body = parsed.body[:BODY_CHARS]
    return (
        f"From: {parsed.from_address}\n"
        f"Subject: {parsed.subject}\n"
        f"Attachments: {names}\n\n"
        f"{body}"
    )


def _known_label(raw: str | None) -> EmailLabel | None:
    if raw is None:
        return None
    try:
        label = EmailLabel(raw.strip())
    except ValueError:
        return None
    if label not in CLASSIFIER_LABELS:
        return None
    return label


def _label_agent() -> Agent[None, LabelDecision]:
    key = settings.typesafe_api_key
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is required to label email")
    model = TypeSafeModel(
        settings.typesafe_label_model,
        provider=TypeSafeProvider(api_key=key),
    )
    return Agent(model, output_type=LabelDecision)


def label_with_jev(prompt: str) -> str | None:
    try:
        result = _label_agent().run_sync(prompt)
    except (AgentRunError, UnexpectedModelBehavior) as exc:
        log.warning("email_label_model_error", error=type(exc).__name__)
        return None
    return result.output.label

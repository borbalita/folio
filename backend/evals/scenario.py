"""The structured scenario every generated email and case is derived from."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from ingest.email.labels import CLASSIFIER_LABELS, newsletter_match

OWNER_NAME = "Anna Weber"
OWNER_ADDRESS = "anna@example.com"
EMAILS_PER_LABEL = 12
MIN_UNANSWERABLE = 8
HISTORY_DAYS = 120


class TrapKind(StrEnum):
    NEAR_DUPLICATE = "near_duplicate"
    DATE_BOUNDARY = "date_boundary"
    BORDERLINE_LABEL = "borderline_label"


MIN_TRAPS = {
    TrapKind.NEAR_DUPLICATE: 4,
    TrapKind.DATE_BOUNDARY: 4,
    TrapKind.BORDERLINE_LABEL: 6,
}

# Fields have no defaults: the models double as OpenAI strict structured-output schemas.


class Sender(BaseModel):
    key: str = Field(description="Short stable id, e.g. 's_landlord'.")
    name: str
    address: str = Field(description="Email address on a domain ending in .example.")
    organization: str | None


class Fact(BaseModel):
    name: str = Field(description="What the fact is, e.g. 'amount due', 'due date'.")
    value: str = Field(
        description=(
            "The exact text that must appear in the email body, e.g. '€1,240.00', "
            "'14 October 2026', 'INV-20931'."
        )
    )


class Trap(BaseModel):
    kind: TrapKind
    related_keys: list[str] = Field(
        description="Other emails this trap pairs with (near-duplicates); may be empty."
    )
    note: str = Field(description="Why this email is hard, in one sentence.")


class ScenarioEmail(BaseModel):
    key: str = Field(description="Stable id 'e01', 'e02', ...")
    label: Literal["needs_reply", "promotional", "newsletter", "invoice", "other"]
    sender_key: str
    sent_at: AwareDatetime = Field(description="ISO 8601 with UTC offset.")
    subject: str
    brief: str = Field(description="What the email says, two to four sentences.")
    facts: list[Fact] = Field(description="One to four checkable details.")
    body_format: Literal["plain", "html"]
    in_reply_to: str | None = Field(description="Key of the email this replies to.")
    traps: list[Trap]


class UnanswerableTopic(BaseModel):
    key: str = Field(description="Stable id 'u01', 'u02', ...")
    topic: str = Field(
        description="What the user might ask about that no email answers."
    )
    near_miss_keys: list[str] = Field(
        description="Emails that look related but do not answer it; may be empty."
    )


class ScenarioDraft(BaseModel):
    """What the scenario model writes. The fixed reference date is added in code."""

    senders: list[Sender]
    emails: list[ScenarioEmail]
    unanswerable: list[UnanswerableTopic]


class ScenarioExtension(BaseModel):
    """New senders and hard-to-label emails added to an existing scenario."""

    senders: list[Sender]
    emails: list[ScenarioEmail]


class Scenario(ScenarioDraft):
    today: date
    owner_name: str
    owner_address: str


def scenario_problems(scenario: Scenario) -> list[str]:
    """Everything that makes a scenario unusable. Empty means valid."""
    problems: list[str] = []
    sender_keys = {sender.key for sender in scenario.senders}
    email_keys = {email.key for email in scenario.emails}
    problems += _duplicates("sender", [sender.key for sender in scenario.senders])
    problems += _duplicates("email", [email.key for email in scenario.emails])
    problems += _duplicates("topic", [topic.key for topic in scenario.unanswerable])

    for sender in scenario.senders:
        if not sender.address.lower().endswith(".example"):
            problems.append(f"sender {sender.key}: {sender.address} is not on .example")
        if newsletter_match(sender.address) is not None:
            problems.append(f"sender {sender.key}: matches an AI newsletter rule")

    earliest = scenario.today - timedelta(days=HISTORY_DAYS)
    for email in scenario.emails:
        where = f"email {email.key}"
        if email.sender_key not in sender_keys:
            problems.append(f"{where}: unknown sender {email.sender_key}")
        if not email.sent_at.date() < scenario.today or email.sent_at.date() < earliest:
            problems.append(
                f"{where}: sent_at {email.sent_at} outside the history window"
            )
        if not 1 <= len(email.facts) <= 4:
            problems.append(f"{where}: needs one to four facts")
        if email.in_reply_to is not None and email.in_reply_to not in email_keys:
            problems.append(f"{where}: replies to unknown {email.in_reply_to}")
        for trap in email.traps:
            for key in trap.related_keys:
                if key not in email_keys or key == email.key:
                    problems.append(f"{where}: trap refers to unknown {key}")

    counts = Counter(email.label for email in scenario.emails)
    for label in CLASSIFIER_LABELS:
        if abs(counts[label.value] - EMAILS_PER_LABEL) > 2:
            problems.append(f"label {label.value}: {counts[label.value]} emails")

    traps = Counter(trap.kind for email in scenario.emails for trap in email.traps)
    for kind, minimum in MIN_TRAPS.items():
        if traps[kind] < minimum:
            problems.append(f"trap {kind.value}: {traps[kind]} < {minimum}")

    if len(scenario.unanswerable) < MIN_UNANSWERABLE:
        problems.append(f"only {len(scenario.unanswerable)} unanswerable topics")
    for topic in scenario.unanswerable:
        for key in topic.near_miss_keys:
            if key not in email_keys:
                problems.append(f"topic {topic.key}: unknown near miss {key}")
    return problems


def extension_problems(
    scenario: Scenario, extension: ScenarioExtension, per_label: int
) -> list[str]:
    """An extension adds only borderline-label emails, so RAG cases stay unchanged."""
    problems: list[str] = []
    counts = Counter(email.label for email in extension.emails)
    for label in CLASSIFIER_LABELS:
        if counts[label.value] != per_label:
            problems.append(
                f"new label {label.value}: {counts[label.value]} != {per_label}"
            )
    for email in extension.emails:
        kinds = [trap.kind for trap in email.traps]
        if kinds != [TrapKind.BORDERLINE_LABEL]:
            problems.append(
                f"email {email.key}: needs exactly one borderline_label trap"
            )
        if email.in_reply_to is not None:
            problems.append(f"email {email.key}: must not be a reply")
    old_values = {fact.value for email in scenario.emails for fact in email.facts}
    for email in extension.emails:
        for fact in email.facts:
            if fact.value in old_values:
                problems.append(f"email {email.key}: repeats fact value {fact.value!r}")
    return problems + scenario_problems(extend(scenario, extension))


def extend(scenario: Scenario, extension: ScenarioExtension) -> Scenario:
    return scenario.model_copy(
        update={
            "senders": scenario.senders + extension.senders,
            "emails": scenario.emails + extension.emails,
        }
    )


def _duplicates(kind: str, keys: list[str]) -> list[str]:
    return [f"duplicate {kind} key {key}" for key, n in Counter(keys).items() if n > 1]

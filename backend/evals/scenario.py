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


class FactRef(BaseModel):
    email_key: str
    fact_name: str = Field(description="The `name` of one of that email's facts.")


class PlannedQuestion(BaseModel):
    """A question whose answer is fixed by scenario facts, possibly across emails."""

    key: str = Field(description="Stable id 'q01', 'q02', ...")
    kind: Literal["multi_email", "superseded", "vague", "unanswerable"]
    ask: str = Field(
        description=(
            "What the person wants to know, as an instruction for whoever words the "
            "question, including how it must refer to people and time."
        )
    )
    answer_facts: list[FactRef] = Field(description="Empty for unanswerable questions.")
    distractor_keys: list[str] = Field(
        description="Emails that look like they answer but don't (outdated values, look-alikes)."
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


class StoryExtension(BaseModel):
    """Linked emails, filler mail, and planned questions that make retrieval harder."""

    senders: list[Sender]
    emails: list[ScenarioEmail]
    questions: list[PlannedQuestion]


class Scenario(ScenarioDraft):
    today: date
    owner_name: str
    owner_address: str
    questions: list[PlannedQuestion] = []


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
    average = len(scenario.emails) / len(CLASSIFIER_LABELS)
    for label in CLASSIFIER_LABELS:
        if abs(counts[label.value] - average) > max(2, average / 4):
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


def story_problems(
    scenario: Scenario, extension: StoryExtension, minimums: dict[str, int]
) -> list[str]:
    """Planned questions must resolve to scenario facts; v1 facts must stay unambiguous."""
    problems: list[str] = []
    combined = extend(scenario, extension)
    emails = {email.key: email for email in combined.emails}
    # Only the same kind of fact with the same value could answer a v1 question;
    # a shared date under another fact name is harmless.
    old_facts = {(f.name, f.value) for email in scenario.emails for f in email.facts}
    new_keys = {email.key for email in extension.emails}
    for email in extension.emails:
        if email.traps:
            problems.append(f"email {email.key}: new emails carry no traps")
        if email.in_reply_to is not None and email.in_reply_to not in new_keys:
            problems.append(f"email {email.key}: may only reply to a new email")
        for fact in email.facts:
            if (fact.name, fact.value) in old_facts:
                problems.append(
                    f"email {email.key}: repeats v1 fact {fact.name} = {fact.value!r}"
                )
    counts = Counter(question.kind for question in extension.questions)
    for kind, minimum in minimums.items():
        if counts[kind] < minimum:
            problems.append(f"questions {kind}: {counts[kind]} < {minimum}")
    problems += _duplicates("question", [q.key for q in combined.questions])
    for question in extension.questions:
        where = f"question {question.key}"
        for key in question.distractor_keys:
            if key not in emails:
                problems.append(f"{where}: unknown distractor {key}")
        resolved = [_resolve(emails, ref) for ref in question.answer_facts]
        for ref, fact in zip(question.answer_facts, resolved, strict=True):
            if fact is None:
                problems.append(
                    f"{where}: no fact {ref.fact_name!r} in {ref.email_key}"
                )
        answer_keys = {ref.email_key for ref in question.answer_facts}
        if question.kind == "unanswerable" and question.answer_facts:
            problems.append(f"{where}: unanswerable questions have no answer facts")
        if question.kind != "unanswerable" and not question.answer_facts:
            problems.append(f"{where}: needs answer facts")
        if question.kind == "multi_email" and len(answer_keys) < 2:
            problems.append(f"{where}: multi_email needs facts from two or more emails")
        if question.kind == "superseded":
            problems += _superseded_problems(where, question, emails, new_keys)
        if answer_keys & set(question.distractor_keys):
            problems.append(f"{where}: an answer email is also a distractor")
    return problems + scenario_problems(combined)


def _resolve(emails: dict[str, ScenarioEmail], ref: FactRef) -> Fact | None:
    email = emails.get(ref.email_key)
    if email is None:
        return None
    return next((fact for fact in email.facts if fact.name == ref.fact_name), None)


def _superseded_problems(
    where: str,
    question: PlannedQuestion,
    emails: dict[str, ScenarioEmail],
    new_keys: set[str],
) -> list[str]:
    """A new email changes a value from an earlier new email; v1 answers never change.

    Other distractors (look-alikes) may be v1 emails.
    """
    for ref in question.answer_facts:
        current = _resolve(emails, ref)
        if current is None or ref.email_key not in new_keys:
            continue
        for key in question.distractor_keys:
            older = emails.get(key) if key in new_keys else None
            if older is None or older.sent_at >= emails[ref.email_key].sent_at:
                continue
            if any(
                f.name == ref.fact_name and f.value != current.value
                for f in older.facts
            ):
                return []
    return [
        (
            f"{where}: superseded needs a new answer email and an earlier new distractor "
            "with the same fact name and an outdated value"
        )
    ]


def extend(
    scenario: Scenario, extension: ScenarioExtension | StoryExtension
) -> Scenario:
    questions = extension.questions if isinstance(extension, StoryExtension) else []
    return scenario.model_copy(
        update={
            "senders": scenario.senders + extension.senders,
            "emails": scenario.emails + extension.emails,
            "questions": scenario.questions + questions,
        }
    )


def _duplicates(kind: str, keys: list[str]) -> list[str]:
    return [f"duplicate {kind} key {key}" for key, n in Counter(keys).items() if n > 1]

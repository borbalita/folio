"""RAG and labelling cases, derived in code from the scenario. Only question wording uses an LLM."""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.config import settings
from evals.fixtures import A_ACTIVE
from evals.scenario import Fact, Scenario, ScenarioEmail, TrapKind
from ingest.email.labels import CLASSIFIER_LABELS

Split = Literal["tuning", "held_out"]
CaseKind = Literal[
    "fact",
    "near_duplicate",
    "date_boundary",
    "unanswerable",
    "multi_email",
    "superseded",
    "vague",
]
FACTS_PER_CASE = 2
FACT_CASES_PER_LABEL = 2


class ProbeFilters(BaseModel):
    since: date | None = None
    until: date | None = None
    label: str | None = None
    sender: str | None = None
    mailbox: str | None = None


class RagIntent(BaseModel):
    """Everything about a case except its wording."""

    case_id: str
    kind: CaseKind
    ask: str
    context: str
    expected_email_keys: list[str]
    expected_facts: list[Fact]
    distractor_keys: list[str]
    filters: ProbeFilters
    forbidden_terms: list[str] = []
    """Words the question must not use, e.g. sender names in a vague question."""


class RagCase(BaseModel):
    case_id: str
    kind: CaseKind
    question: str
    today: date
    user_id: UUID
    mailbox_id: UUID
    probe_query: str
    probe_filters: ProbeFilters
    expected_email_keys: list[str]
    expected_facts: list[Fact]
    answerable: bool
    distractor_keys: list[str]
    split: Split


class LabelCase(BaseModel):
    email_key: str
    expected_label: str
    split: Split


def held_out(index: int) -> bool:
    """Two of every five positions: about 60/40 tuning/held-out within each group."""
    return index % 5 in (1, 3)


def label_cases(scenario: Scenario) -> list[LabelCase]:
    by_label: dict[str, list[ScenarioEmail]] = defaultdict(list)
    # Natural key order, so adding e100+ in a later data version keeps earlier splits.
    for email in sorted(scenario.emails, key=lambda e: (len(e.key), e.key)):
        by_label[email.label].append(email)
    return [
        LabelCase(
            email_key=email.key,
            expected_label=label.value,
            split="held_out" if held_out(index) else "tuning",
        )
        for label in CLASSIFIER_LABELS
        for index, email in enumerate(by_label[label.value])
    ]


def rag_intents(scenario: Scenario) -> list[RagIntent]:
    emails = {email.key: email for email in scenario.emails}
    near_duplicates = _near_duplicate_intents(scenario, emails)
    targeted = {key for intent in near_duplicates for key in intent.expected_email_keys}
    intents = (
        near_duplicates
        + _date_boundary_intents(scenario, skip=targeted)
        + _fact_intents(scenario)
        + _unanswerable_intents(scenario)
        + _planned_intents(scenario, emails)
    )
    return [
        intent.model_copy(update={"case_id": f"c{n:02d}"})
        for n, intent in enumerate(intents, start=1)
    ]


def rag_case(
    intent: RagIntent, question: str, scenario: Scenario, split: Split
) -> RagCase:
    return RagCase(
        case_id=intent.case_id,
        kind=intent.kind,
        question=question,
        today=scenario.today,
        user_id=A_ACTIVE.user_id,
        mailbox_id=A_ACTIVE.id,
        probe_query=question,
        probe_filters=intent.filters,
        expected_email_keys=intent.expected_email_keys,
        expected_facts=intent.expected_facts,
        answerable=intent.kind != "unanswerable",
        distractor_keys=intent.distractor_keys,
        split=split,
    )


def rag_splits(intents: list[RagIntent]) -> dict[str, Split]:
    """Balanced by case kind, so every trap type appears in both splits."""
    by_kind: dict[str, list[str]] = defaultdict(list)
    for intent in intents:
        by_kind[intent.kind].append(intent.case_id)
    return {
        case_id: "held_out" if held_out(index) else "tuning"
        for case_ids in by_kind.values()
        for index, case_id in enumerate(case_ids)
    }


def question_problems(
    question: str, intent: RagIntent, scenario: Scenario
) -> list[str]:
    """A question must not give away a fact value or copy an email subject."""
    lowered = question.casefold()
    problems = [
        f"contains the answer {fact.value!r}"
        for fact in intent.expected_facts
        if fact.value.casefold() in lowered
    ]
    problems += [
        f"names {term!r}; refer to them by role instead"
        for term in intent.forbidden_terms
        if re.search(rf"\b{re.escape(term.casefold())}\b", lowered)
    ]
    subjects = {
        e.subject for e in scenario.emails if e.key in intent.expected_email_keys
    }
    problems += [
        f"copies the subject {subject!r}"
        for subject in subjects
        if subject.casefold().removeprefix("re: ") in lowered
    ]
    return problems


def _near_duplicate_intents(
    scenario: Scenario, emails: dict[str, ScenarioEmail]
) -> list[RagIntent]:
    pairs: list[tuple[str, str]] = []
    for email in scenario.emails:
        for trap in email.traps:
            if trap.kind != TrapKind.NEAR_DUPLICATE:
                continue
            for other in trap.related_keys:
                pair = tuple(sorted((email.key, other)))
                if pair not in pairs:
                    pairs.append(pair)
    intents = []
    for index, (first, second) in enumerate(pairs):
        # Alternate which of the pair is asked about, so "the latest" isn't always right.
        target, partner = (emails[second], emails[first])
        if index % 2:
            target, partner = partner, target
        facts = _differing_facts(target, partner)
        if _month(local_date(target)) != _month(local_date(partner)):
            cue = f"the one sent in {_month(local_date(target))}; name the month"
        elif target.sent_at > partner.sent_at:
            cue = "the most recent one; say latest or updated"
        else:
            cue = "the first one; say original or first"
        intents.append(
            _intent(
                scenario,
                "near_duplicate",
                target,
                facts,
                ask=(
                    f"Ask for the {_names(facts)} in the email from {_sender(scenario, target)}. "
                    f"A similar email from the same sender exists; ask about {cue}."
                ),
                distractors=[partner.key],
            )
        )
    return intents


def _date_boundary_intents(scenario: Scenario, *, skip: set[str]) -> list[RagIntent]:
    intents = []
    for email in scenario.emails:
        if email.key in skip or not any(
            trap.kind == TrapKind.DATE_BOUNDARY for trap in email.traps
        ):
            continue
        local = local_date(email)
        first = local.replace(day=1)
        last = local.replace(day=calendar.monthrange(local.year, local.month)[1])
        facts = email.facts[:FACTS_PER_CASE]
        intents.append(
            _intent(
                scenario,
                "date_boundary",
                email,
                facts,
                ask=(
                    f"Ask for the {_names(facts)} from the mail Anna got from "
                    f"{_sender(scenario, email)} in {_month(local)}. "
                    "Name the month explicitly."
                ),
                filters=ProbeFilters(since=first, until=last),
            )
        )
    return intents


def _fact_intents(scenario: Scenario) -> list[RagIntent]:
    used = {
        key
        for email in scenario.emails
        if email.traps or email.in_reply_to
        for key in (email.key, email.in_reply_to)
        if key
    }
    used |= {key for topic in scenario.unanswerable for key in topic.near_miss_keys}
    intents = []
    for label in CLASSIFIER_LABELS:
        candidates = [
            e for e in scenario.emails if e.label == label.value and e.key not in used
        ]
        for email in candidates[:FACT_CASES_PER_LABEL]:
            facts = email.facts[:FACTS_PER_CASE]
            intents.append(
                _intent(
                    scenario,
                    "fact",
                    email,
                    facts,
                    ask=f"Ask for the {_names(facts)} in the email from {_sender(scenario, email)}.",
                )
            )
    return intents


def _unanswerable_intents(scenario: Scenario) -> list[RagIntent]:
    return [
        RagIntent(
            case_id="",
            kind="unanswerable",
            ask=f"Ask this in your own words: {topic.topic}",
            context="No email answers this.",
            expected_email_keys=[],
            expected_facts=[],
            distractor_keys=topic.near_miss_keys,
            filters=ProbeFilters(),
        )
        for topic in scenario.unanswerable
    ]


PLANNED_ASK_SUFFIX = {
    "multi_email": "The answer is spread over several emails; ask for all of it in one question.",
    "superseded": "Ask for the current, latest value.",
    "vague": (
        "Do not name the sender, their organisation, or an exact date or month; "
        "refer to them by role and relative time from today."
    ),
    "unanswerable": "No email answers this.",
}


def _planned_intents(
    scenario: Scenario, emails: dict[str, ScenarioEmail]
) -> list[RagIntent]:
    intents = []
    for question in scenario.questions:
        facts = [
            next(f for f in emails[ref.email_key].facts if f.name == ref.fact_name)
            for ref in question.answer_facts
        ]
        keys = list(dict.fromkeys(ref.email_key for ref in question.answer_facts))
        forbidden: list[str] = []
        if question.kind == "vague":
            for key in keys:
                sender = next(
                    s for s in scenario.senders if s.key == emails[key].sender_key
                )
                forbidden += [sender.name, sender.name.split()[0]]
                if sender.organization:
                    forbidden.append(sender.organization)
        intents.append(
            RagIntent(
                case_id="",
                kind=question.kind,
                ask=f"{question.ask} {PLANNED_ASK_SUFFIX[question.kind]}",
                context="\n\n".join(_masked_context(emails[key]) for key in keys)
                or "No email answers this.",
                expected_email_keys=keys,
                expected_facts=facts,
                distractor_keys=question.distractor_keys,
                filters=ProbeFilters(),
                forbidden_terms=list(dict.fromkeys(forbidden)),
            )
        )
    return intents


def _intent(
    scenario: Scenario,
    kind: CaseKind,
    email: ScenarioEmail,
    facts: list[Fact],
    *,
    ask: str,
    distractors: list[str] | None = None,
    filters: ProbeFilters | None = None,
) -> RagIntent:
    return RagIntent(
        case_id="",
        kind=kind,
        ask=ask,
        context=_masked_context(email),
        expected_email_keys=[email.key],
        expected_facts=facts,
        distractor_keys=distractors or [],
        filters=filters or ProbeFilters(),
    )


def _masked_context(email: ScenarioEmail) -> str:
    """Subject and brief with every fact value replaced by its name, so wording can't leak answers."""
    text = f"Subject: {email.subject}\n{email.brief}"
    for fact in email.facts:
        text = text.replace(fact.value, f"[{fact.name}]")
    return text


def _differing_facts(target: ScenarioEmail, partner: ScenarioEmail) -> list[Fact]:
    partner_values = {fact.value for fact in partner.facts}
    differing = [fact for fact in target.facts if fact.value not in partner_values]
    return (differing or target.facts)[:FACTS_PER_CASE]


def _sender(scenario: Scenario, email: ScenarioEmail) -> str:
    sender = next(s for s in scenario.senders if s.key == email.sender_key)
    return (
        f"{sender.name} ({sender.organization})" if sender.organization else sender.name
    )


def _names(facts: list[Fact]) -> str:
    return " and ".join(fact.name for fact in facts)


def local_date(email: ScenarioEmail) -> date:
    return email.sent_at.astimezone(ZoneInfo(settings.email_timezone)).date()


def _month(day: date) -> str:
    return day.strftime("%B %Y")

from __future__ import annotations

from datetime import datetime

from evals.scenario import (
    Fact,
    Scenario,
    ScenarioEmail,
    ScenarioExtension,
    Trap,
    TrapKind,
    extend,
    extension_problems,
    scenario_problems,
)
from ingest.email.labels import CLASSIFIER_LABELS
from tests.evals.conftest import BERLIN_SUMMER, make_email


def test_valid_scenario_has_no_problems(valid_scenario: Scenario) -> None:
    assert scenario_problems(valid_scenario) == []


def test_unknown_references_are_reported(valid_scenario: Scenario) -> None:
    email = valid_scenario.emails[0]
    email.sender_key = "s_ghost"
    email.in_reply_to = "e999"
    email.traps.append(
        Trap(kind=TrapKind.NEAR_DUPLICATE, related_keys=["e998"], note="")
    )
    valid_scenario.unanswerable[0].near_miss_keys = ["e997"]

    problems = scenario_problems(valid_scenario)

    assert any("unknown sender s_ghost" in p for p in problems)
    assert any("replies to unknown e999" in p for p in problems)
    assert any("unknown e998" in p for p in problems)
    assert any("unknown near miss e997" in p for p in problems)


def test_missing_trap_kind_is_reported(valid_scenario: Scenario) -> None:
    for email in valid_scenario.emails:
        email.traps = [t for t in email.traps if t.kind != TrapKind.DATE_BOUNDARY]

    assert any("trap date_boundary" in p for p in scenario_problems(valid_scenario))


def test_unbalanced_labels_are_reported(valid_scenario: Scenario) -> None:
    valid_scenario.emails = [e for e in valid_scenario.emails if e.label != "invoice"]

    assert "label invoice: 0 emails" in scenario_problems(valid_scenario)


def test_mail_after_today_is_reported(valid_scenario: Scenario) -> None:
    valid_scenario.emails[0].sent_at = datetime(2026, 10, 1, 8, 0, tzinfo=BERLIN_SUMMER)

    assert any(
        "outside the history window" in p for p in scenario_problems(valid_scenario)
    )


def test_real_or_ai_newsletter_domains_are_reported(valid_scenario: Scenario) -> None:
    valid_scenario.senders[0].address = "dan@tldrnewsletter.com"

    problems = scenario_problems(valid_scenario)

    assert any("is not on .example" in p for p in problems)
    assert any("AI newsletter" in p for p in problems)


def test_too_few_unanswerable_topics_are_reported(valid_scenario: Scenario) -> None:
    valid_scenario.unanswerable = valid_scenario.unanswerable[:2]

    assert "only 2 unanswerable topics" in scenario_problems(valid_scenario)


def _hard(key: str, label: str, value: str) -> ScenarioEmail:
    return make_email(
        key,
        label,
        facts=[Fact(name="code", value=value)],
        traps=[
            Trap(
                kind=TrapKind.BORDERLINE_LABEL,
                related_keys=[],
                note="looks like an invoice",
            )
        ],
    )


def _extension() -> ScenarioExtension:
    return ScenarioExtension(
        senders=[],
        emails=[
            _hard(f"h{n}", label.value, f"HARD-{n}")
            for n, label in enumerate(CLASSIFIER_LABELS)
        ],
    )


def test_valid_extension_has_no_problems(valid_scenario: Scenario) -> None:
    extension = _extension()

    assert extension_problems(valid_scenario, extension, per_label=1) == []
    assert (
        len(extend(valid_scenario, extension).emails) == len(valid_scenario.emails) + 5
    )


def test_extension_must_only_add_borderline_emails(valid_scenario: Scenario) -> None:
    extension = _extension()
    extension.emails[0].traps = [
        Trap(kind=TrapKind.DATE_BOUNDARY, related_keys=[], note="")
    ]
    extension.emails[1].facts = [Fact(name="amount", value="€42.00")]
    extension.emails.pop()

    problems = extension_problems(valid_scenario, extension, per_label=1)

    assert "email h0: needs exactly one borderline_label trap" in problems
    assert "email h1: repeats fact value '€42.00'" in problems
    assert "new label other: 0 != 1" in problems

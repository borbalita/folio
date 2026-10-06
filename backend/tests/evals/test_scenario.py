from __future__ import annotations

from datetime import datetime

from evals.scenario import Scenario, Trap, TrapKind, scenario_problems
from tests.evals.conftest import BERLIN_SUMMER


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

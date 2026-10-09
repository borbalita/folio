from __future__ import annotations

from collections import Counter
from datetime import date, datetime

import pytest

from evals.cases import (
    RagIntent,
    label_cases,
    question_problems,
    rag_case,
    rag_intents,
    rag_splits,
)
from evals.scenario import Fact, Scenario, Sender, Trap, TrapKind, UnanswerableTopic
from tests.evals.conftest import BERLIN_SUMMER, make_email


def _trap(kind: TrapKind, *related: str) -> Trap:
    return Trap(kind=kind, related_keys=list(related), note="")


@pytest.fixture
def scenario() -> Scenario:
    july = make_email(
        "e01",
        "invoice",
        sender_key="s_power",
        sent_at=datetime(2026, 7, 3, 9, 0, tzinfo=BERLIN_SUMMER),
        subject="Your July electricity invoice",
        brief="Invoice LS-07 totals €51.35.",
        facts=[
            Fact(name="invoice number", value="LS-07"),
            Fact(name="amount", value="€51.35"),
        ],
        traps=[_trap(TrapKind.NEAR_DUPLICATE, "e02")],
    )
    august = make_email(
        "e02",
        "invoice",
        sender_key="s_power",
        sent_at=datetime(2026, 8, 3, 9, 0, tzinfo=BERLIN_SUMMER),
        subject="Your August electricity invoice",
        facts=[
            Fact(name="invoice number", value="LS-08"),
            Fact(name="amount", value="€51.35"),
        ],
        traps=[_trap(TrapKind.NEAR_DUPLICATE, "e01")],
    )
    # 00:30 in Berlin on 1 August is still 31 July in UTC.
    boundary = make_email(
        "e03",
        "other",
        sent_at=datetime(2026, 8, 1, 0, 30, tzinfo=BERLIN_SUMMER),
        facts=[Fact(name="parcel number", value="PX-1")],
        traps=[_trap(TrapKind.DATE_BOUNDARY)],
    )
    plain = make_email("e04", "promotional", facts=[Fact(name="code", value="SAVE10")])
    near_miss = make_email("e05", "promotional")
    return Scenario(
        senders=[
            Sender(
                key="s_shop", name="Shop", address="a@shop.example", organization=None
            ),
            Sender(
                key="s_power",
                name="Billing",
                address="b@power.example",
                organization="Power",
            ),
        ],
        emails=[july, august, boundary, plain, near_miss],
        unanswerable=[
            UnanswerableTopic(key="u01", topic="My water bill?", near_miss_keys=["e05"])
        ],
        today=date(2026, 10, 1),
        owner_name="Anna Weber",
        owner_address="anna@example.com",
    )


def _by_kind(intents: list[RagIntent]) -> dict[str, list[RagIntent]]:
    grouped: dict[str, list[RagIntent]] = {}
    for intent in intents:
        grouped.setdefault(intent.kind, []).append(intent)
    return grouped


def test_near_duplicate_case_expects_one_email_with_its_partner_as_distractor(
    scenario: Scenario,
) -> None:
    (case,) = _by_kind(rag_intents(scenario))["near_duplicate"]

    assert case.expected_email_keys == ["e02"]
    assert case.distractor_keys == ["e01"]
    # The shared amount can't tell the two apart, so only the differing fact is asked.
    assert [fact.value for fact in case.expected_facts] == ["LS-08"]
    assert "August 2026" in case.ask


def test_date_boundary_case_filters_by_the_local_month(scenario: Scenario) -> None:
    (case,) = _by_kind(rag_intents(scenario))["date_boundary"]

    assert case.expected_email_keys == ["e03"]
    assert (case.filters.since, case.filters.until) == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )


def test_fact_cases_skip_trap_and_near_miss_emails(scenario: Scenario) -> None:
    facts = _by_kind(rag_intents(scenario))["fact"]

    assert [case.expected_email_keys for case in facts] == [["e04"]]


def test_unanswerable_case_has_no_expected_mail(scenario: Scenario) -> None:
    (intent,) = _by_kind(rag_intents(scenario))["unanswerable"]

    case = rag_case(intent, "What was my water bill?", scenario, "tuning")

    assert case.answerable is False
    assert case.expected_email_keys == []
    assert case.expected_facts == []
    assert case.distractor_keys == ["e05"]


def test_case_ids_are_unique_and_every_expected_key_exists(scenario: Scenario) -> None:
    intents = rag_intents(scenario)
    keys = {email.key for email in scenario.emails}

    assert len({intent.case_id for intent in intents}) == len(intents)
    for intent in intents:
        assert set(intent.expected_email_keys + intent.distractor_keys) <= keys


def test_context_hides_fact_values(scenario: Scenario) -> None:
    for intent in rag_intents(scenario):
        for fact in intent.expected_facts:
            assert fact.value not in intent.context


def test_question_giving_away_an_answer_or_subject_is_rejected(
    scenario: Scenario,
) -> None:
    (intent,) = _by_kind(rag_intents(scenario))["near_duplicate"]

    assert (
        question_problems(
            "What's the number on my August power bill?", intent, scenario
        )
        == []
    )
    assert question_problems("Is LS-08 my August bill?", intent, scenario) == [
        "contains the answer 'LS-08'"
    ]
    assert question_problems(
        "What's in 'your august electricity invoice'?", intent, scenario
    ) == ["copies the subject 'Your August electricity invoice'"]


def test_label_cases_split_about_60_40_within_each_label(
    valid_scenario: Scenario,
) -> None:
    cases = label_cases(valid_scenario)

    counts = Counter((case.expected_label, case.split) for case in cases)
    for label in {case.expected_label for case in cases}:
        assert (counts[(label, "tuning")], counts[(label, "held_out")]) == (7, 5)


def test_label_splits_of_existing_emails_survive_three_digit_keys(
    valid_scenario: Scenario,
) -> None:
    emails = [make_email(f"e{n:02d}", "needs_reply") for n in range(1, 13)]
    v1 = valid_scenario.model_copy(update={"emails": emails})
    v2 = v1.model_copy(update={"emails": emails + [make_email("e100", "needs_reply")]})
    before = {case.email_key: case.split for case in label_cases(v1)}

    after = {case.email_key: case.split for case in label_cases(v2)}

    assert {key: after[key] for key in before} == before


def test_rag_splits_put_every_kind_in_both_splits(valid_scenario: Scenario) -> None:
    intents = rag_intents(valid_scenario)
    splits = rag_splits(intents)

    for kind in {intent.kind for intent in intents}:
        kind_splits = {splits[i.case_id] for i in intents if i.kind == kind}
        assert kind_splits == {"tuning", "held_out"}

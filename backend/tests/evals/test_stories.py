from __future__ import annotations

from datetime import datetime

import pytest

from evals.cases import question_problems, rag_intents
from evals.scenario import (
    Fact,
    FactRef,
    PlannedQuestion,
    Scenario,
    Sender,
    StoryExtension,
    extend,
    story_problems,
)
from tests.evals.conftest import BERLIN_SUMMER, make_email

NO_MINIMUMS: dict[str, int] = {}


def _question(key: str, kind: str, refs: list[tuple[str, str]], distractors: list[str]):
    return PlannedQuestion(
        key=key,
        kind=kind,
        ask="Ask about it.",
        answer_facts=[FactRef(email_key=e, fact_name=n) for e, n in refs],
        distractor_keys=distractors,
    )


@pytest.fixture
def story() -> StoryExtension:
    proposed = make_email(
        "n1",
        "needs_reply",
        sender_key="s_mira",
        sent_at=datetime(2026, 9, 1, 9, 0, tzinfo=BERLIN_SUMMER),
        facts=[Fact(name="meeting time", value="10:00")],
    )
    moved = make_email(
        "n2",
        "needs_reply",
        sender_key="s_mira",
        sent_at=datetime(2026, 9, 3, 9, 0, tzinfo=BERLIN_SUMMER),
        in_reply_to="n1",
        facts=[
            Fact(name="meeting time", value="15:30"),
            Fact(name="room", value="Atelier 2"),
        ],
    )
    return StoryExtension(
        senders=[
            Sender(
                key="s_mira",
                name="Mira Falk",
                address="mira@formhaven.example",
                organization="Formhaven Studio",
            )
        ],
        emails=[proposed, moved],
        questions=[
            _question("q01", "superseded", [("n2", "meeting time")], ["n1"]),
            _question(
                "q02", "multi_email", [("n1", "meeting time"), ("n2", "room")], []
            ),
            _question("q03", "vague", [("n2", "room")], []),
            _question("q04", "unanswerable", [], ["n1"]),
        ],
    )


def test_valid_story_has_no_problems(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    assert story_problems(valid_scenario, story, NO_MINIMUMS) == []


def test_unknown_fact_reference_is_reported(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    story.questions[1].answer_facts[1].fact_name = "colour"

    assert "question q02: no fact 'colour' in n2" in story_problems(
        valid_scenario, story, NO_MINIMUMS
    )


def test_superseded_needs_an_earlier_outdated_value(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    story.emails[0].facts = [Fact(name="meeting time", value="15:30")]

    problems = story_problems(valid_scenario, story, NO_MINIMUMS)

    assert any("superseded needs a new answer email" in p for p in problems)


def test_new_mail_may_not_touch_v1(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    v1_key = valid_scenario.emails[0].key
    story.emails[1].in_reply_to = v1_key
    story.emails[1].facts.append(Fact(name="amount", value="€42.00"))
    story.questions[0].distractor_keys = [v1_key]

    problems = story_problems(valid_scenario, story, NO_MINIMUMS)

    assert "email n2: may only reply to a new email" in problems
    assert "email n2: repeats v1 fact amount = '€42.00'" in problems
    assert any(
        p.startswith("question q01: superseded needs a new answer email")
        for p in problems
    )


def test_v1_value_under_another_fact_name_is_allowed(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    story.emails[1].facts.append(Fact(name="deposit", value="€42.00"))

    assert story_problems(valid_scenario, story, NO_MINIMUMS) == []


def test_multi_email_needs_two_emails_and_minimums_are_enforced(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    story.questions[1].answer_facts = story.questions[1].answer_facts[:1]

    problems = story_problems(valid_scenario, story, {"vague": 3})

    assert "question q02: multi_email needs facts from two or more emails" in problems
    assert "questions vague: 1 < 3" in problems


def test_planned_questions_become_cases_after_the_derived_ones(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    before = rag_intents(valid_scenario)

    after = rag_intents(extend(valid_scenario, story))

    assert after[: len(before)] == before
    planned = {i.kind: i for i in after[len(before) :]}
    assert planned["superseded"].expected_email_keys == ["n2"]
    assert [f.value for f in planned["superseded"].expected_facts] == ["15:30"]
    assert planned["superseded"].distractor_keys == ["n1"]
    assert planned["multi_email"].expected_email_keys == ["n1", "n2"]
    assert planned["unanswerable"].expected_email_keys == []


def test_vague_question_naming_the_sender_is_rejected(
    valid_scenario: Scenario, story: StoryExtension
) -> None:
    scenario = extend(valid_scenario, story)
    vague = next(i for i in rag_intents(scenario) if i.kind == "vague")

    assert question_problems("Which room did my colleague pick?", vague, scenario) == []
    assert question_problems("Which room did Mira pick?", vague, scenario) == [
        "names 'Mira'; refer to them by role instead"
    ]
    assert question_problems("Did Formhaven Studio move it?", vague, scenario) == [
        "names 'Formhaven Studio'; refer to them by role instead"
    ]

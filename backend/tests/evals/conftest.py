from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from evals.scenario import (
    EMAILS_PER_LABEL,
    MIN_TRAPS,
    MIN_UNANSWERABLE,
    Fact,
    Scenario,
    ScenarioEmail,
    Sender,
    Trap,
    UnanswerableTopic,
)
from ingest.email.labels import CLASSIFIER_LABELS

BERLIN_SUMMER = timezone(timedelta(hours=2))


def make_email(key: str, label: str, **overrides: object) -> ScenarioEmail:
    values: dict[str, object] = {
        "key": key,
        "label": label,
        "sender_key": "s_shop",
        "sent_at": datetime(2026, 9, 15, 9, 30, tzinfo=BERLIN_SUMMER),
        "subject": f"Subject {key}",
        "brief": "A short brief.",
        "facts": [Fact(name="amount", value="€42.00")],
        "body_format": "plain",
        "in_reply_to": None,
        "traps": [],
    }
    values.update(overrides)
    return ScenarioEmail.model_validate(values)


@pytest.fixture
def valid_scenario() -> Scenario:
    emails = [
        make_email(f"e{label.value}{n}", label.value)
        for label in CLASSIFIER_LABELS
        for n in range(EMAILS_PER_LABEL)
    ]
    trap_index = 0
    for kind, minimum in MIN_TRAPS.items():
        for _ in range(minimum):
            emails[trap_index].traps.append(
                Trap(kind=kind, related_keys=[emails[trap_index + 1].key], note="hard")
            )
            trap_index += 1
    return Scenario(
        senders=[
            Sender(
                key="s_shop",
                name="Shop",
                address="hello@shop.example",
                organization="Shop GmbH",
            )
        ],
        emails=emails,
        unanswerable=[
            UnanswerableTopic(key=f"u{n}", topic="water bill", near_miss_keys=[])
            for n in range(MIN_UNANSWERABLE)
        ],
        today=date(2026, 10, 1),
        owner_name="Anna Weber",
        owner_address="anna@example.com",
    )

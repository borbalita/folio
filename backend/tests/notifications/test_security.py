from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import structlog
from openai import APIConnectionError

from app.notifications import security
from app.notifications.security import Candidate, Classification, ItemVerdict, Verdicts

EMAIL = uuid.uuid4()
OTHER = uuid.uuid4()
CANDIDATES = [
    Candidate(EMAIL, 0, date(2026, 11, 4), "tldr", "PHP2Shell exploited", "Active attacks."),
    Candidate(EMAIL, 1, date(2026, 11, 4), "tldr", "Lab raises money", "Big round."),
    Candidate(OTHER, 7, date(2026, 11, 5), "alpha_signal", "PHP2Shell patch out", ""),
]


def _completion(parsed: Verdicts | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


def test_results_are_keyed_by_email_and_position() -> None:
    verdicts = Verdicts(
        items=[
            ItemVerdict(index=0, security=True, alert="new"),
            ItemVerdict(index=1, security=False, alert=None),
            ItemVerdict(index=2, security=True, alert="update"),
        ]
    )

    assert security.parse(verdicts, CANDIDATES) == [
        Classification(EMAIL, 0, True, "new"),
        Classification(EMAIL, 1, False, None),
        Classification(OTHER, 7, True, "update"),
    ]


def test_an_unknown_index_is_dropped_and_the_rest_kept() -> None:
    verdicts = Verdicts(
        items=[
            ItemVerdict(index=0, security=True, alert="new"),
            ItemVerdict(index=9, security=True, alert="new"),
            ItemVerdict(index=-1, security=True, alert="new"),
            ItemVerdict(index=1, security=False, alert=None),
        ]
    )

    result = security.parse(verdicts, CANDIDATES)

    assert [(c.email_id, c.position) for c in result] == [(EMAIL, 0), (EMAIL, 1)]


def test_a_repeated_index_keeps_the_first_answer() -> None:
    verdicts = Verdicts(
        items=[
            ItemVerdict(index=0, security=True, alert="new"),
            ItemVerdict(index=0, security=False, alert=None),
        ]
    )

    assert security.parse(verdicts, CANDIDATES) == [Classification(EMAIL, 0, True, "new")]


def test_an_alert_status_on_a_non_security_item_is_ignored() -> None:
    verdicts = Verdicts(items=[ItemVerdict(index=1, security=False, alert="new")])

    assert security.parse(verdicts, CANDIDATES) == [Classification(EMAIL, 1, False, None)]


def test_items_the_model_left_out_are_not_classified() -> None:
    verdicts = Verdicts(items=[ItemVerdict(index=0, security=False, alert=None)])

    assert [c.position for c in security.parse(verdicts, CANDIDATES)] == [0]


def test_the_prompt_carries_the_scope_the_items_and_the_recent_alerts() -> None:
    [system, user] = security.classification_messages(CANDIDATES, ["Old flaw exploited"])

    for phrase in ("sandbox", "active exploitation", "bug bounty", "routine patches", "repeat"):
        assert phrase in system["content"]
    assert "Old flaw exploited" in user["content"]
    assert "[0]" in user["content"] and "PHP2Shell exploited" in user["content"]
    assert "[2]" in user["content"] and "PHP2Shell patch out" in user["content"]


def test_a_failed_call_logs_only_its_type_and_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(candidates, alerts):
        raise APIConnectionError(request=MagicMock())

    monkeypatch.setattr(security, "request_classification", fail)
    # A logger no earlier test has used, so it can't be cached outside the capture.
    monkeypatch.setattr(security, "log", structlog.get_logger())

    with structlog.testing.capture_logs() as logs:
        result = security.classify(CANDIDATES, [])

    assert result is None
    assert logs == [
        {"event": "news_classification_failed", "error": "APIConnectionError", "log_level": "warning"}
    ]


def test_an_answer_without_parsed_output_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "request_classification", lambda c, a: _completion(None))

    assert security.classify(CANDIDATES, []) is None


def test_one_call_classifies_the_whole_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    verdicts = Verdicts(items=[ItemVerdict(index=0, security=True, alert="new")])
    monkeypatch.setattr(
        security, "request_classification", lambda c, a: calls.append((c, a)) or _completion(verdicts)
    )

    result = security.classify(CANDIDATES, ["x"])

    assert result == [Classification(EMAIL, 0, True, "new")]
    assert calls == [(CANDIDATES, ["x"])]

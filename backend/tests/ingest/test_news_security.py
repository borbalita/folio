from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.notifications import security, store
from app.notifications.security import Candidate, Classification
from ingest import news_security

TODAY = date(2026, 11, 5)


def _candidate(day: date, position: int = 0) -> Candidate:
    return Candidate(uuid.uuid4(), position, day, "tldr", f"T{position}", "b")


def _run(monkeypatch: pytest.MonkeyPatch, by_day: dict[date, list[Candidate]], *, fail: set[date] = frozenset()):
    asked: list[tuple[list[Candidate], list[str]]] = []
    loads: list[tuple[date, date | None]] = []

    def load(session, since, until=None):
        loads.append((since, until))
        return by_day.get(since, [])

    def classify(candidates, alerts):
        asked.append((candidates, alerts))
        if candidates[0].edition_date in fail:
            return None
        # The model also guesses an alert status, which the backfill must not keep.
        return [Classification(c.email_id, c.position, True, "new") for c in candidates]

    monkeypatch.setattr(store, "load_unclassified", load)
    monkeypatch.setattr(security, "classify", classify)
    session = MagicMock()
    counts = news_security.backfill(session, days=5, today=TODAY)
    return counts, asked, loads, session


def test_each_day_is_one_call_with_no_alert_history_oldest_day_first(monkeypatch: pytest.MonkeyPatch) -> None:
    d1, d2 = date(2026, 10, 31), date(2026, 11, 1)
    by_day = {d1: [_candidate(d1, 0), _candidate(d1, 1)], d2: [_candidate(d2, 0)]}

    counts, asked, loads, _ = _run(monkeypatch, by_day)

    assert [(batch[0].edition_date, len(batch), alerts) for batch, alerts in asked] == [
        (d1, 2, []),
        (d2, 1, []),
    ]
    assert loads[0] == (date(2026, 10, 31), date(2026, 11, 1))
    assert counts == {"days": 3, "classified": 3, "failed_days": 0}


def test_the_last_two_days_are_left_to_the_notify_step(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, loads, _ = _run(monkeypatch, {})

    assert loads[-1][0] == date(2026, 11, 2)
    assert all(since < date(2026, 11, 3) for since, _ in loads)


def test_the_backfill_stores_security_only_and_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    d1 = date(2026, 10, 31)

    _, _, _, session = _run(monkeypatch, {d1: [_candidate(d1)]})

    statements = [call.args[0] for call in session.execute.call_args_list]
    assert statements, "nothing was written"
    for statement in statements:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert sql.startswith("INSERT INTO news_item_notes")
        assert "alert_status" not in sql
        assert "notifications " not in sql.replace("news_item_notes", "")
        assert "alert_status" not in statement.compile(dialect=postgresql.dialect()).params
    session.commit.assert_called()


def test_a_failed_day_is_counted_and_the_other_days_still_run(monkeypatch: pytest.MonkeyPatch) -> None:
    d1, d2 = date(2026, 10, 31), date(2026, 11, 1)
    by_day = {d1: [_candidate(d1)], d2: [_candidate(d2)]}

    counts, asked, _, _ = _run(monkeypatch, by_day, fail={d1})

    assert len(asked) == 2
    assert counts["failed_days"] == 1 and counts["classified"] == 1


def test_a_demo_free_query_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """The backfill loads items through the same query the notify step uses."""
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    news_security.backfill(session, days=3, today=TODAY)

    sql = str(
        session.execute.call_args_list[0].args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "mailboxes.provider != 'demo'" in sql
    assert "news_item_notes.security IS NULL" in sql


def test_the_days_argument_is_required_to_be_positive() -> None:
    with pytest.raises(SystemExit):
        news_security.main(["--days", "0"])

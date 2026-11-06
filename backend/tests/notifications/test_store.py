from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.notifications import store
from app.notifications.detect import NewNotification


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_insert_rows_ignores_keys_already_recorded() -> None:
    session = MagicMock()

    store.insert_rows(session, [NewNotification("invoice_new:x", "invoice_new", "pending", "t")])

    sql = _sql(session.execute.call_args.args[0])
    assert sql.startswith("INSERT INTO notifications")
    assert "ON CONFLICT (key) DO NOTHING" in sql


def test_insert_rows_with_nothing_does_not_touch_the_database() -> None:
    session = MagicMock()

    store.insert_rows(session, [])

    session.execute.assert_not_called()


def test_enabled_needs_all_three_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "1")
    monkeypatch.setattr(settings, "app_url", "https://folio.test")
    assert store.telegram_enabled()

    monkeypatch.setattr(settings, "telegram_chat_id", None)
    assert not store.telegram_enabled()


def test_record_uses_berlin_date_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    inv = SimpleNamespace(
        id=uuid.uuid4(), email_id=uuid.uuid4(), status="open", payee="P",
        amount=Decimal("1.00"), currency="EUR", due_date=date(2026, 10, 20),
    )
    monkeypatch.setattr(store, "load_invoices", lambda session: [store.invoice_facts(inv, "s@x")])
    monkeypatch.setattr(store, "load_stories", lambda session, since: seen.setdefault("since", since) and [])
    monkeypatch.setattr(store, "known_keys", lambda session: set())

    def plan(invoices, stories, known, *, today, app_url, enabled):
        seen["today"] = today
        return [NewNotification("invoice_new:1", "invoice_new", "pending", "t")]

    monkeypatch.setattr(store, "plan_notifications", plan)
    session = MagicMock()

    # 23:30 UTC on the 19th is already the 20th in Berlin.
    added = store.record_notifications(session, datetime(2026, 10, 19, 23, 30, tzinfo=UTC))

    assert seen["today"] == date(2026, 10, 20)
    assert seen["since"] == date(2026, 10, 18)
    assert added == 1
    session.commit.assert_called_once()



def test_only_recent_big_stories_are_read() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_stories(session, since=date(2026, 10, 17))

    sql = _sql(session.execute.call_args.args[0])
    assert "news_stories.is_big IS true" in sql
    assert "news_stories.last_seen >= " in sql


def test_load_invoices_skips_demo_mailboxes() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_invoices(session)

    statement = session.execute.call_args.args[0]
    sql = _sql(statement)
    assert "mailboxes.provider !=" in sql
    params = statement.compile(dialect=postgresql.dialect()).params
    assert "demo" in params.values()


def test_big_stories_exclude_demo_mailboxes() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_stories(session, date(2026, 10, 1))

    statement = session.execute.call_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "JOIN emails ON emails.id = news_items.email_id" in sql
    assert "JOIN mailboxes ON mailboxes.id = emails.mailbox_id" in sql
    assert "mailboxes.provider != 'demo'" in sql


def test_load_editions_maps_email_ids_to_whole_bodies() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    session = MagicMock()
    session.execute.return_value.all.return_value = [(first, "body one"), (second, "body two")]

    editions = store.load_editions(session, [first, second])

    assert editions == {first: "body one", second: "body two"}
    sql = _sql(session.execute.call_args.args[0])
    assert "emails.body" in sql and "emails.id IN" in sql


def test_load_editions_with_no_emails_does_not_touch_the_database() -> None:
    session = MagicMock()

    assert store.load_editions(session, []) == {}
    session.execute.assert_not_called()


def test_the_message_and_its_note_come_from_one_explanation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications.detect import NewsItemFacts
    from app.notifications.summary import NewsSummary

    item = NewsItemFacts(
        id=uuid.uuid4(), email_id=uuid.uuid4(), position=4, source="tldr",
        title="T", blurb="B", url="https://x.test",
    )
    row = NewNotification("news:k", "news_big", "pending", "fallback", (item,))
    monkeypatch.setattr(store, "load_editions", lambda session, ids: {item.email_id: "body"})
    monkeypatch.setattr(store.summary, "explain", lambda items, editions, **_: NewsSummary(headline="H", summary="S."))

    new_row, note = store.explained(MagicMock(), row)

    assert new_row.text == "📰 H\nS.\nTLDR: https://x.test"
    assert note == {"email_id": item.email_id, "position": 4, "headline": "H", "explanation": "S."}


def test_a_failed_explanation_sends_the_fallback_and_stores_no_note(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications.detect import NewsItemFacts

    item = NewsItemFacts(
        id=uuid.uuid4(), email_id=uuid.uuid4(), position=4, source="tldr",
        title="T", blurb="B", url="",
    )
    row = NewNotification("news:k", "news_big", "pending", "fallback", (item,))
    monkeypatch.setattr(store, "load_editions", lambda session, ids: {})
    monkeypatch.setattr(store.summary, "explain", lambda items, editions, **_: None)

    new_row, note = store.explained(MagicMock(), row)

    assert new_row.text == "📰 T\nB"
    assert note is None


def test_notes_are_upserted_without_touching_the_security_columns() -> None:
    session = MagicMock()

    store.save_notes(
        session,
        [{"email_id": uuid.uuid4(), "position": 1, "headline": "H", "explanation": "S."}],
    )

    sql = _sql(session.execute.call_args.args[0])
    assert sql.startswith("INSERT INTO news_item_notes")
    assert "ON CONFLICT (email_id, position) DO UPDATE" in sql
    assert "headline = excluded.headline" in sql and "explanation = excluded.explanation" in sql
    assert "security" not in sql.split("DO UPDATE")[1]


def test_saving_no_notes_does_not_touch_the_database() -> None:
    session = MagicMock()

    store.save_notes(session, [])

    session.execute.assert_not_called()


def _literal(statement) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _candidate(position: int = 0):
    from app.notifications.security import Candidate

    return Candidate(uuid.uuid4(), position, date(2026, 11, 4), "tldr", f"T{position}", "b")


def test_stories_are_the_big_ones_and_those_with_a_security_alert() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_stories(session, date(2026, 10, 1))

    sql = _literal(session.execute.call_args.args[0])
    assert "news_stories.is_big IS true" in sql
    assert "news_item_notes.alert_status IN ('new', 'update')" in sql
    assert " OR " in sql


def test_unclassified_items_are_the_recent_non_demo_ones_without_a_verdict() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_unclassified(session, date(2026, 11, 3))

    sql = _literal(session.execute.call_args.args[0])
    assert "mailboxes.provider != 'demo'" in sql
    assert "news_items.edition_date >= '2026-11-03'" in sql
    assert "news_item_notes.security IS NULL" in sql
    # Matched by newsletter and position, which survive re-embedding, never by item id.
    assert "news_item_notes.email_id = news_items.email_id" in sql
    assert "news_item_notes.position = news_items.position" in sql
    assert "news_items.id" not in sql.split("WHERE")[0].split("LEFT OUTER JOIN")[1]


def test_a_day_batch_is_bounded_on_both_sides() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    store.load_unclassified(session, date(2026, 10, 5), until=date(2026, 10, 6))

    sql = _literal(session.execute.call_args.args[0])
    assert "news_items.edition_date >= '2026-10-05'" in sql
    assert "news_items.edition_date < '2026-10-06'" in sql


def test_recent_alerts_are_the_last_seven_days_of_new_and_update_headlines() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = [("Flaw A",), ("Flaw B",)]

    headlines = store.load_recent_alerts(session, date(2026, 11, 5))

    assert headlines == ["Flaw A", "Flaw B"]
    sql = _literal(session.execute.call_args.args[0])
    assert "news_items.edition_date >= '2026-10-29'" in sql
    assert "news_item_notes.alert_status IN ('new', 'update')" in sql


def _classify(monkeypatch, *, candidates, answer):
    from app.notifications import security

    calls, saved = [], []
    monkeypatch.setattr(store, "load_unclassified", lambda session, since, until=None: candidates)
    monkeypatch.setattr(store, "load_recent_alerts", lambda session, today: ["Old alert"])
    monkeypatch.setattr(
        security, "classify", lambda items, alerts: calls.append((items, alerts)) or answer
    )
    monkeypatch.setattr(store, "save_classifications", lambda session, rows: saved.extend(rows))
    session = MagicMock()
    count = store.classify_recent(session, datetime(2026, 11, 5, 9, tzinfo=UTC))
    return count, calls, saved, session


def test_new_items_get_one_call_and_their_results_are_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications.security import Classification

    candidates = [_candidate(0), _candidate(1)]
    answer = [
        Classification(candidates[0].email_id, 0, True, "new"),
        Classification(candidates[1].email_id, 1, False, None),
    ]

    count, calls, saved, session = _classify(monkeypatch, candidates=candidates, answer=answer)

    assert calls == [(candidates, ["Old alert"])]
    assert saved == answer
    assert count == 2
    session.commit.assert_called_once()


def test_nothing_to_classify_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    count, calls, saved, _ = _classify(monkeypatch, candidates=[], answer=[])

    assert (count, calls, saved) == (0, [], [])


def test_a_failed_classification_stores_nothing_and_the_next_run_asks_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [_candidate(0)]

    count, _, saved, session = _classify(monkeypatch, candidates=candidates, answer=None)
    second = _classify(monkeypatch, candidates=candidates, answer=None)

    assert count == 0 and saved == []
    session.commit.assert_not_called()
    assert second[1] == [(candidates, ["Old alert"])]


def test_classification_looks_back_two_days(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    monkeypatch.setattr(
        store, "load_unclassified", lambda session, since, until=None: seen.setdefault("since", since) and []
    )

    store.classify_recent(MagicMock(), datetime(2026, 11, 5, 23, 30, tzinfo=UTC))

    # 23:30 UTC is already the 6th in Berlin.
    assert seen["since"] == date(2026, 11, 4)


def test_classifications_upsert_only_the_security_columns() -> None:
    from app.notifications.security import Classification

    session = MagicMock()

    store.save_classifications(session, [Classification(uuid.uuid4(), 1, True, "new")])

    sql = _sql(session.execute.call_args.args[0])
    assert "ON CONFLICT (email_id, position) DO UPDATE" in sql
    update = sql.split("DO UPDATE")[1]
    assert "security = excluded.security" in update
    assert "alert_status = excluded.alert_status" in update
    assert "headline" not in update and "explanation" not in update


def test_the_backfill_writes_security_without_touching_alert_status() -> None:
    from app.notifications.security import Classification

    session = MagicMock()

    store.save_security_only(session, [Classification(uuid.uuid4(), 1, True, "update")])

    statement = session.execute.call_args.args[0]
    sql = _sql(statement)
    assert "alert_status" not in sql
    assert "security = excluded.security" in sql.split("DO UPDATE")[1]
    assert "alert_status" not in statement.compile(dialect=postgresql.dialect()).params


def test_a_security_message_is_written_with_the_security_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications.detect import NewsItemFacts
    from app.notifications.summary import NewsSummary

    item = NewsItemFacts(
        id=uuid.uuid4(), email_id=uuid.uuid4(), position=2, source="tldr",
        title="T", blurb="B", url="https://x.test", alert_status="update",
    )
    row = NewNotification("news:k", "news_security", "pending", "fallback", (item,), update=True)
    seen = {}
    monkeypatch.setattr(store, "load_editions", lambda session, ids: {})

    def explain(items, editions, *, security=False):
        seen["security"] = security
        return NewsSummary(headline="H", summary="S. Patch now.")

    monkeypatch.setattr(store.summary, "explain", explain)

    new_row, note = store.explained(MagicMock(), row)

    assert seen["security"] is True
    assert new_row.text == "🔒 Update: H\nS. Patch now.\nTLDR: https://x.test"
    assert note["headline"] == "H"
    assert "security" not in note and "alert_status" not in note


def test_a_failed_security_explanation_falls_back_with_the_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications.detect import NewsItemFacts

    item = NewsItemFacts(
        id=uuid.uuid4(), email_id=uuid.uuid4(), position=2, source="tldr",
        title="T", blurb="B", url="", alert_status="new",
    )
    row = NewNotification("news:k", "news_security", "pending", "fallback", (item,))
    monkeypatch.setattr(store, "load_editions", lambda session, ids: {})
    monkeypatch.setattr(store.summary, "explain", lambda items, editions, **_: None)

    new_row, note = store.explained(MagicMock(), row)

    assert new_row.text == "🔒 T\nB"
    assert note is None


def _db_row(item, *, big: bool, alert: str | None, story: uuid.UUID):
    stored = SimpleNamespace(
        story_id=story, email_id=item.email_id, position=item.position, id=item.id,
        source=item.source, title=item.title, blurb=item.blurb, url=item.url,
    )
    return SimpleNamespace(NewsItem=stored, is_big=big, alert_status=alert)


def test_database_rows_become_alerts_through_the_planner() -> None:
    from app.notifications.detect import NewsItemFacts, plan_notifications

    def facts(title: str) -> NewsItemFacts:
        return NewsItemFacts(
            id=uuid.uuid4(), email_id=uuid.uuid4(), position=0, source="tldr",
            title=title, blurb="b", url="https://tldr.test/x",
        )

    repeat, update, big_new = facts("Repeat"), facts("Update"), facts("Big new")
    rows = [
        _db_row(repeat, big=False, alert="repeat", story=uuid.uuid4()),
        _db_row(update, big=False, alert="update", story=uuid.uuid4()),
        _db_row(big_new, big=True, alert="new", story=uuid.uuid4()),
    ]
    session = MagicMock()
    session.execute.return_value.all.return_value = rows

    stories = store.load_stories(session, date(2026, 11, 3))
    planned = plan_notifications(
        [], stories, set(), today=date(2026, 11, 5), app_url="https://folio.test", enabled=True
    )

    sent = {r.text.split("\n")[0]: r.kind for r in planned if r.status == "pending"}
    assert sent == {"🔒 Update: Update": "news_security", "🔒 Big new": "news_security"}
    assert "Repeat" not in " ".join(r.key for r in planned if r.status == "pending")
    assert [r.key for r in planned if "Repeat" in r.text] == []


def test_a_big_story_without_an_alert_is_still_sent_as_big_from_rows() -> None:
    from app.notifications.detect import NewsItemFacts, plan_notifications

    item = NewsItemFacts(
        id=uuid.uuid4(), email_id=uuid.uuid4(), position=0, source="tldr",
        title="Plain big", blurb="b", url="",
    )
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        _db_row(item, big=True, alert=None, story=uuid.uuid4())
    ]

    planned = plan_notifications(
        [], store.load_stories(session, date(2026, 11, 3)), set(),
        today=date(2026, 11, 5), app_url="", enabled=True,
    )

    assert [(r.kind, r.text.split("\n")[0]) for r in planned] == [("news_big", "📰 Plain big")]

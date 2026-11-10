from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.database import news_feed
from app.database.news_feed import FeedItem, build_days, items_statement

BEFORE = date(2026, 11, 6)


def _item(
    story: str,
    day: date,
    *,
    source: str = "tldr",
    position: int = 0,
    title: str = "Title",
    blurb: str = "Blurb.",
    url: str = "",
    big: bool = False,
    security: bool = False,
    headline: str | None = None,
    explanation: str | None = None,
    email_id: uuid.UUID | None = None,
) -> FeedItem:
    return FeedItem(
        id=uuid.uuid4(),
        email_id=email_id or uuid.uuid4(),
        position=position,
        source=source,
        edition_date=day,
        title=title,
        blurb=blurb,
        url=url,
        story_id=uuid.uuid5(uuid.NAMESPACE_OID, story),
        is_big=big,
        headline=headline,
        explanation=explanation,
        security=security,
    )


def _titles(days: list[dict]) -> list[tuple[str, list[str]]]:
    return [(day["date"], [story["title"] for story in day["stories"]]) for day in days]


def test_a_story_with_items_on_two_days_appears_once_on_the_newer_day() -> None:
    items = [
        _item("a", date(2026, 11, 3), title="A early"),
        _item("a", date(2026, 11, 5), title="A late", source="alpha_signal"),
    ]

    days = build_days(items, before=BEFORE, days=14)

    assert [day["date"] for day in days] == ["2026-11-05"]
    assert len(days[0]["stories"]) == 1
    assert len(days[0]["stories"][0]["items"]) == 2


def test_a_story_crossing_the_window_boundary_is_on_one_page_only() -> None:
    # Window 1 is 2026-10-30..11-05 (before 11-06, 7 days); window 2 is 10-23..10-29.
    items = [
        _item("a", date(2026, 10, 29), title="A old"),
        _item("a", date(2026, 10, 31), title="A new", source="alpha_signal"),
        _item("b", date(2026, 10, 28), title="B"),
    ]

    first = build_days(items, before=BEFORE, days=7)
    second = build_days(items, before=date(2026, 10, 30), days=7)

    assert _titles(first) == [("2026-10-31", ["A old"])]
    assert _titles(second) == [("2026-10-28", ["B"])]


def test_only_big_keeps_stories_both_newsletters_cover() -> None:
    items = [
        _item("a", date(2026, 11, 5), title="Big one", big=True),
        _item("b", date(2026, 11, 5), title="Small one"),
    ]

    days = build_days(items, before=BEFORE, days=14, only="big")

    assert _titles(days) == [("2026-11-05", ["Big one"])]
    assert days[0]["stories"][0]["badges"] == ["big"]


def test_the_blurb_is_the_longest_non_empty_one() -> None:
    items = [
        _item("a", date(2026, 11, 5), blurb=""),
        _item("a", date(2026, 11, 5), blurb="Short.", source="alpha_signal", position=2),
        _item("a", date(2026, 11, 4), blurb="A longer blurb.", position=1),
    ]

    (day,) = build_days(items, before=BEFORE, days=14)

    assert day["stories"][0]["blurb"] == "A longer blurb."


def test_a_story_whose_blurbs_are_all_empty_has_an_empty_blurb() -> None:
    (day,) = build_days([_item("a", date(2026, 11, 5), blurb="")], before=BEFORE, days=14)

    assert day["stories"][0]["blurb"] == ""


def test_the_explanation_survives_re_embedding_and_rebuilding() -> None:
    email_id = uuid.uuid4()
    notes = {(email_id, 4): ("Model X launches", "It is fast, which matters because...")}
    # After re-embedding, the item has a new id and the story a new id; email and position stay.
    before = _item("old-story", date(2026, 11, 5), email_id=email_id, position=4, title="Raw")
    rebuilt = _item(
        "new-story",
        date(2026, 11, 5),
        email_id=email_id,
        position=4,
        title="Raw",
        headline=notes[(email_id, 4)][0],
        explanation=notes[(email_id, 4)][1],
    )

    assert build_days([before], before=BEFORE, days=14)[0]["stories"][0]["explanation"] is None
    (day,) = build_days([rebuilt], before=BEFORE, days=14)
    story = day["stories"][0]
    assert story["title"] == "Model X launches"
    assert story["explanation"] == "It is fast, which matters because..."


def test_without_a_stored_headline_the_title_is_the_first_items() -> None:
    items = [
        _item("a", date(2026, 11, 4), title="Oldest title"),
        _item("a", date(2026, 11, 5), title="Newest title", source="alpha_signal"),
    ]

    (day,) = build_days(items, before=BEFORE, days=14)

    assert day["stories"][0]["title"] == "Oldest title"


def test_within_a_day_big_comes_first_then_newsletter_order() -> None:
    day = date(2026, 11, 5)
    items = [
        _item("a", day, title="TLDR 1", position=1),
        _item("b", day, title="TLDR 0", position=0),
        _item("c", day, title="Big", position=7, source="alpha_signal", big=True),
    ]

    (result,) = build_days(items, before=BEFORE, days=14)

    assert [story["title"] for story in result["stories"]] == ["Big", "TLDR 0", "TLDR 1"]


def test_days_are_newest_first() -> None:
    items = [_item("a", date(2026, 11, 3)), _item("b", date(2026, 11, 5))]

    days = build_days(items, before=BEFORE, days=14)

    assert [day["date"] for day in days] == ["2026-11-05", "2026-11-03"]


def test_links_are_one_per_newsletter_and_skip_newsletters_without_one() -> None:
    items = [
        _item("a", date(2026, 11, 5), url="https://tldr.test/a"),
        _item("a", date(2026, 11, 5), url="https://tldr.test/other", position=2),
        _item("a", date(2026, 11, 5), url="", source="alpha_signal", position=3),
    ]

    (day,) = build_days(items, before=BEFORE, days=14)

    assert day["stories"][0]["links"] == [
        {"source": "tldr", "name": "TLDR", "url": "https://tldr.test/a"}
    ]


def test_item_refs_name_the_email_and_position() -> None:
    item = _item("a", date(2026, 11, 5), position=3)

    (day,) = build_days([item], before=BEFORE, days=14)

    assert day["stories"][0]["items"] == [{"emailId": str(item.email_id), "position": 3}]


def _loader_sql() -> str:
    statement = items_statement(
        [uuid.UUID(int=1)], start=date(2026, 10, 1), before=date(2026, 11, 1)
    )
    return str(statement.compile(dialect=postgresql.dialect()))


def test_the_outer_query_is_scoped_to_the_mailboxes_as_well_as_the_window() -> None:
    # A story can be shared with other users' mailboxes: the items read for it must still be
    # the user's own, so the outer WHERE needs the filter, not only the window subquery.
    outer_where = _loader_sql().split("\nWHERE ", 1)[1]

    assert outer_where.startswith("emails.mailbox_id IN (__[POSTCOMPILE_mailbox_id_1]) AND ")


def test_the_window_reads_all_items_of_every_story_that_touches_it() -> None:
    sql = _loader_sql()

    assert "news_items.story_id IN (SELECT news_items.story_id" in sql
    window = sql.split("news_items.story_id IN (SELECT", 1)[1].split(") OR ", 1)[0]
    assert "emails.mailbox_id IN" in window
    assert "news_items.edition_date >= " in window and "news_items.edition_date < " in window


def test_notes_are_joined_on_the_email_and_position_not_on_ids() -> None:
    sql = _loader_sql()

    assert (
        "LEFT OUTER JOIN news_item_notes ON news_item_notes.email_id = news_items.email_id "
        "AND news_item_notes.position = news_items.position"
    ) in sql


class _FakeSession:
    def __init__(self, rows: list[SimpleNamespace], older: bool) -> None:
        self.rows, self.older = rows, older

    def execute(self, statement: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.rows)

    def scalar(self, statement: object) -> bool:
        return self.older


def _row(item: FeedItem, *, is_big: bool | None = False) -> SimpleNamespace:
    stored = SimpleNamespace(
        id=item.id, email_id=item.email_id, position=item.position, source=item.source,
        edition_date=item.edition_date, title=item.title, blurb=item.blurb, url=item.url,
        story_id=item.story_id,
    )
    return SimpleNamespace(
        NewsItem=stored, is_big=is_big, headline=item.headline, explanation=item.explanation,
        security=item.security,
    )


def _list(monkeypatch: pytest.MonkeyPatch, rows: list[SimpleNamespace], older: bool) -> dict:
    @contextmanager
    def session():
        yield _FakeSession(rows, older)

    monkeypatch.setattr(news_feed, "get_session", session)
    return news_feed.list_stories(
        [uuid.UUID(int=1)], before=BEFORE, days=7, only=None
    )


def test_list_stories_maps_rows_and_points_to_the_next_page(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _item("a", date(2026, 11, 5), title="Raw", headline="Stored", explanation="Why.")

    result = _list(monkeypatch, [_row(item, is_big=True)], older=True)

    assert result["nextBefore"] == "2026-10-30"
    (day,) = result["days"]
    assert day["date"] == "2026-11-05"
    assert day["stories"][0]["title"] == "Stored"
    assert day["stories"][0]["explanation"] == "Why."
    assert day["stories"][0]["badges"] == ["big"]


def test_list_stories_has_no_next_page_when_nothing_is_older(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _item("a", date(2026, 11, 5))

    result = _list(monkeypatch, [_row(item, is_big=None)], older=False)

    assert result["nextBefore"] is None
    assert result["days"][0]["stories"][0]["badges"] == []


def test_a_security_story_has_the_badge_and_a_story_can_be_both() -> None:
    items = [
        _item("a", date(2026, 11, 5), security=True, position=1),
        _item("b", date(2026, 11, 5), security=True, big=True, position=2),
        _item("c", date(2026, 11, 5), position=3),
    ]

    (day,) = build_days(items, before=BEFORE, days=14)

    badges = {story["items"][0]["position"]: story["badges"] for story in day["stories"]}
    assert badges == {1: ["security"], 2: ["big", "security"], 3: []}


def test_one_security_item_marks_the_whole_story() -> None:
    items = [
        _item("a", date(2026, 11, 4), position=1),
        _item("a", date(2026, 11, 5), security=True, source="alpha_signal", position=2),
    ]

    (day,) = build_days(items, before=BEFORE, days=14)

    assert day["stories"][0]["badges"] == ["security"]


def test_within_a_day_big_comes_first_then_security_then_newsletter_order() -> None:
    items = [
        _item("plain1", date(2026, 11, 5), position=0, title="Plain 1"),
        _item("sec2", date(2026, 11, 5), position=1, title="Security 2", security=True),
        _item("plain3", date(2026, 11, 5), position=2, title="Plain 3"),
        _item("sec4", date(2026, 11, 5), position=3, title="Security 4", security=True),
        _item("big5", date(2026, 11, 5), position=4, title="Big 5", big=True),
        _item("bigsec6", date(2026, 11, 5), position=5, title="Big security 6", big=True, security=True),
    ]

    days = build_days(items, before=BEFORE, days=14)

    assert _titles(days) == [
        (
            "2026-11-05",
            ["Big 5", "Big security 6", "Security 2", "Security 4", "Plain 1", "Plain 3"],
        )
    ]


def test_only_security_keeps_the_marked_stories() -> None:
    items = [
        _item("a", date(2026, 11, 5), title="Flaw", security=True),
        _item("b", date(2026, 11, 5), title="Funding"),
        _item("c", date(2026, 11, 5), title="Big flaw", security=True, big=True),
    ]

    days = build_days(items, before=BEFORE, days=14, only="security")

    assert _titles(days) == [("2026-11-05", ["Big flaw", "Flaw"])]


def test_the_items_query_reads_the_security_mark_from_the_notes() -> None:
    statement = items_statement([uuid.UUID(int=1)], start=date(2026, 10, 30), before=BEFORE)

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "news_item_notes.security" in sql.split("FROM")[0]

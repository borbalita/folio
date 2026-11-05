from __future__ import annotations

import uuid
from datetime import date

from app.database.news_feed import FeedItem, build_days

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

    days = build_days(items, before=BEFORE, days=14, only_big=True)

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

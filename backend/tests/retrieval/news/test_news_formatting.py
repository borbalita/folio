from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.retrieval.news.formatting import (
    coverage_line,
    format_news_passages,
    format_stories,
)
from app.retrieval.news.retriever import NewsPassage, Story

TLDR_ITEM = UUID("00000000-0000-0000-0000-0000000000a1")
ALPHA_ITEM = UUID("00000000-0000-0000-0000-0000000000a2")
STORY = UUID("00000000-0000-0000-0000-0000000000c1")


def _item(item_id: UUID, source: str) -> NewsPassage:
    return NewsPassage(
        item_id=item_id,
        story_id=STORY,
        source=source,
        edition_date=date(2026, 9, 22),
        title="Robot hands learn to fold laundry",
        blurb="A new policy folds shirts at home.",
        url="https://example.com/robots",
        score=0.0,
    )


def test_empty_texts() -> None:
    assert format_news_passages([]) == "No matching news."
    assert format_stories([], empty="No big stories in that range.") == (
        "No big stories in that range."
    )


def test_item_lists_id_source_edition_title_link_and_blurb() -> None:
    output = format_news_passages([_item(TLDR_ITEM, "tldr")])

    assert f"[{TLDR_ITEM}]" in output
    assert "Source: TLDR" in output
    assert "Edition: 2026-09-22" in output
    assert "Title: Robot hands learn to fold laundry" in output
    assert "Link: https://example.com/robots" in output
    assert output.endswith("A new policy folds shirts at home.")


def test_item_shows_the_demo_newsletter_display_name() -> None:
    output = format_news_passages([_item(ALPHA_ITEM, "demo_tensor")])

    assert "Source: The Daily Tensor" in output
    assert "demo_tensor" not in output


def test_item_falls_back_to_the_raw_source_key() -> None:
    assert "Source: other_news" in format_news_passages(
        [_item(ALPHA_ITEM, "other_news")]
    )


def _story(
    sources: list[str], items: int, first: str, last: str, *, is_big: bool = False
) -> Story:
    return Story(
        story_id=STORY,
        first_seen=date.fromisoformat(first),
        last_seen=date.fromisoformat(last),
        is_big=is_big,
        sources=sources,
        item_count=items,
        items=[],
    )


@pytest.mark.parametrize(
    ("sources", "items", "first", "last", "expected"),
    [
        (
            ["alpha_signal", "tldr"],
            3,
            "2026-10-12",
            "2026-10-14",
            "both newsletters · 3 items · Oct 12–14",
        ),
        (["tldr"], 1, "2026-10-12", "2026-10-12", "TLDR only · 1 item · Oct 12"),
        (
            ["alpha_signal"],
            2,
            "2026-09-30",
            "2026-10-02",
            "Alpha Signal only · 2 items · Sep 30–Oct 2",
        ),
        (
            ["demo_tensor"],
            1,
            "2026-10-12",
            "2026-10-12",
            "The Daily Tensor only · 1 item · Oct 12",
        ),
        (
            ["demo_detective"],
            1,
            "2026-10-12",
            "2026-10-12",
            "AI Detective only · 1 item · Oct 12",
        ),
        (
            ["demo_daily"],
            1,
            "2026-10-12",
            "2026-10-12",
            "demo_daily only · 1 item · Oct 12",
        ),
    ],
)
def test_coverage_line(
    sources: list[str], items: int, first: str, last: str, expected: str
) -> None:
    assert coverage_line(_story(sources, items, first, last)) == expected


def test_format_marks_big_stories_and_lists_every_item_id() -> None:
    story = _story(["alpha_signal", "tldr"], 2, "2026-10-12", "2026-10-12", is_big=True)
    story.items.extend([_item(ALPHA_ITEM, "alpha_signal"), _item(TLDR_ITEM, "tldr")])
    single = _story(["tldr"], 1, "2026-10-13", "2026-10-13")
    single.items.append(_item(TLDR_ITEM, "tldr"))

    output = format_stories([story, single], empty="none")

    assert output.startswith("Big — both newsletters · 2 items · Oct 12\n")
    assert "\n\n---\n\nStory — TLDR only · 1 item · Oct 13\n" in output
    assert f"[{TLDR_ITEM}]" in output
    assert f"[{ALPHA_ITEM}]" in output
    assert f"[{STORY}]" not in output


def _dated(item_id: UUID, day: str) -> NewsPassage:
    return _item(item_id, "tldr").model_copy(
        update={"edition_date": date.fromisoformat(day)}
    )


def _ids_in_order(output: str, ids: list[UUID]) -> list[UUID]:
    return sorted(ids, key=lambda item_id: output.index(f"[{item_id}]"))


def test_search_hits_are_listed_newest_first() -> None:
    old, new, middle = (UUID(int=n) for n in (1, 2, 3))
    passages = [
        _dated(old, "2026-10-08"),
        _dated(new, "2026-10-21"),
        _dated(middle, "2026-10-13"),
    ]

    output = format_news_passages(passages)

    assert _ids_in_order(output, [old, new, middle]) == [new, middle, old]


def test_stories_are_listed_big_first_then_newest_first() -> None:
    old_big = _story(
        ["alpha_signal", "tldr"], 1, "2026-10-08", "2026-10-09", is_big=True
    )
    old_big.items.append(_dated(UUID(int=1), "2026-10-09"))
    new_big = _story(
        ["alpha_signal", "tldr"], 1, "2026-10-20", "2026-10-21", is_big=True
    )
    new_big.items.append(_dated(UUID(int=2), "2026-10-21"))
    newest_small = _story(["tldr"], 1, "2026-10-22", "2026-10-22")
    newest_small.items.append(_dated(UUID(int=3), "2026-10-22"))
    older_small = _story(["tldr"], 1, "2026-10-14", "2026-10-14")
    older_small.items.append(_dated(UUID(int=4), "2026-10-14"))

    output = format_stories([old_big, older_small, new_big, newest_small], empty="none")

    assert _ids_in_order(output, [UUID(int=n) for n in (1, 2, 3, 4)]) == [
        UUID(int=2),
        UUID(int=1),
        UUID(int=3),
        UUID(int=4),
    ]


def test_items_within_a_story_are_listed_newest_first() -> None:
    story = _story(["alpha_signal", "tldr"], 3, "2026-10-14", "2026-10-16", is_big=True)
    story.items.extend(
        [
            _dated(UUID(int=1), "2026-10-14"),
            _dated(UUID(int=2), "2026-10-16"),
            _dated(UUID(int=3), "2026-10-15"),
        ]
    )

    output = format_stories([story], empty="none")

    assert _ids_in_order(output, [UUID(int=n) for n in (1, 2, 3)]) == [
        UUID(int=2),
        UUID(int=3),
        UUID(int=1),
    ]

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.retrieval.news.formatting import format_big_stories, format_news_passages
from app.retrieval.news.retriever import BigStory, NewsPassage

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
    assert format_big_stories([]) == "No big stories in that range."


def test_item_lists_id_source_edition_title_link_and_blurb() -> None:
    output = format_news_passages([_item(TLDR_ITEM, "tldr")])

    assert f"[{TLDR_ITEM}]" in output
    assert "Source: tldr" in output
    assert "Edition: 2026-09-22" in output
    assert "Title: Robot hands learn to fold laundry" in output
    assert "Link: https://example.com/robots" in output
    assert output.endswith("A new policy folds shirts at home.")


def test_story_shows_its_range_both_sources_and_every_item_id() -> None:
    story = BigStory(
        story_id=STORY,
        first_seen=date(2026, 9, 21),
        last_seen=date(2026, 9, 22),
        items=[_item(ALPHA_ITEM, "alpha_signal"), _item(TLDR_ITEM, "tldr")],
    )

    output = format_big_stories([story])

    assert "Story 2026-09-21 to 2026-09-22 (alpha_signal + tldr)" in output
    assert f"[{TLDR_ITEM}]" in output
    assert f"[{ALPHA_ITEM}]" in output
    assert f"[{STORY}]" not in output

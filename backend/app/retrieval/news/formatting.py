"""Text for the news tool responses: items, and stories with their coverage."""

from __future__ import annotations

from datetime import date

from app.retrieval.news.retriever import NewsPassage, Story


def format_news_passages(passages: list[NewsPassage]) -> str:
    if not passages:
        return "No matching news."
    return "\n\n".join(_item_block(passage) for passage in passages)


_NEWSLETTER_NAMES = {"tldr": "TLDR", "alpha_signal": "Alpha Signal"}


def coverage_line(story: Story) -> str:
    """E.g. "both newsletters · 3 items · Oct 12–14" or "TLDR only · 1 item · Oct 12"."""
    if len(story.sources) > 1:
        newsletters = "both newsletters"
    else:
        name = story.sources[0] if story.sources else "unknown"
        newsletters = f"{_NEWSLETTER_NAMES.get(name, name)} only"
    items = f"{story.item_count} item{'' if story.item_count == 1 else 's'}"
    return f"{newsletters} · {items} · {_day_range(story.first_seen, story.last_seen)}"


def format_stories(stories: list[Story], *, empty: str) -> str:
    if not stories:
        return empty
    blocks = []
    for story in stories:
        header = f"{'Big' if story.is_big else 'Story'} — {coverage_line(story)}"
        items = "\n\n".join(_item_block(item) for item in story.items)
        blocks.append(f"{header}\n{items}")
    return "\n\n---\n\n".join(blocks)


def _day_range(first: date, last: date) -> str:
    start = f"{first:%b} {first.day}"
    if first == last:
        return start
    if (first.year, first.month) == (last.year, last.month):
        return f"{start}–{last.day}"
    return f"{start}–{last:%b} {last.day}"


def _item_block(passage: NewsPassage) -> str:
    return "\n".join(
        [
            f"[{passage.item_id}]",
            f"Source: {passage.source}",
            f"Edition: {passage.edition_date.isoformat()}",
            f"Title: {passage.title}",
            f"Link: {passage.url}",
            passage.blurb,
        ]
    )

"""Text for the news tool responses: items, and stories with their coverage."""

from __future__ import annotations

from datetime import date

from app.retrieval.news.retriever import NewsPassage, Story


def format_news_passages(passages: list[NewsPassage]) -> str:
    if not passages:
        return "No matching news."
    return "\n\n".join(_item_block(passage) for passage in _newest_first(passages))


def _newest_first(passages: list[NewsPassage]) -> list[NewsPassage]:
    # Relevance or ranking already chose these; the owner wants them read newest first.
    return sorted(passages, key=lambda passage: passage.edition_date, reverse=True)


_NEWSLETTER_NAMES = {
    "tldr": "TLDR",
    "alpha_signal": "Alpha Signal",
    "demo_tensor": "The Daily Tensor",
    "demo_detective": "AI Detective",
}


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
    # Big stories stay on top, so a briefing still leads with what matters; newest first within.
    ordered = sorted(
        stories, key=lambda story: (story.is_big, story.last_seen), reverse=True
    )
    for story in ordered:
        header = f"{'Big' if story.is_big else 'Story'} — {coverage_line(story)}"
        items = "\n\n".join(_item_block(item) for item in _newest_first(story.items))
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
            f"Source: {_NEWSLETTER_NAMES.get(passage.source, passage.source)}",
            f"Edition: {passage.edition_date.isoformat()}",
            f"Title: {passage.title}",
            f"Link: {passage.url}",
            passage.blurb,
        ]
    )

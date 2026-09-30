"""Text for the search_news and list_big_news tool responses."""

from __future__ import annotations

from app.retrieval.news.retriever import BigStory, NewsPassage


def format_news_passages(passages: list[NewsPassage]) -> str:
    if not passages:
        return "No matching news."
    return "\n\n".join(_item_block(passage) for passage in passages)


def format_big_stories(stories: list[BigStory]) -> str:
    if not stories:
        return "No big stories in that range."
    blocks = []
    for story in stories:
        sources = " + ".join(sorted({item.source for item in story.items}))
        header = (
            f"Story {story.first_seen.isoformat()} to {story.last_seen.isoformat()} "
            f"({sources})"
        )
        items = "\n\n".join(_item_block(item) for item in story.items)
        blocks.append(f"{header}\n{items}")
    return "\n\n---\n\n".join(blocks)


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

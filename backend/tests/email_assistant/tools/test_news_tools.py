from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.database import mailboxes
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.tools.news import execute_list_big_news, execute_search_news
from app.retrieval.news.queries import NewsSearchFilters
from app.retrieval.news.retriever import BigStory, NewsPassage, NewsRetriever

USER = UUID("00000000-0000-0000-0000-000000000001")
THREAD = UUID("00000000-0000-0000-0000-000000000002")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
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
        score=0.5,
    )


class _News(NewsRetriever):
    def __init__(self) -> None:
        self.filters: NewsSearchFilters | None = None

    def search(self, query, *, filters, session=None):  # type: ignore[override]
        self.filters = filters
        if not filters.mailbox_ids:
            return []
        return [_item(TLDR_ITEM, "tldr")]

    def big_stories(self, *, filters, session=None):  # type: ignore[override]
        self.filters = filters
        if not filters.mailbox_ids:
            return []
        return [
            BigStory(
                story_id=STORY,
                first_seen=date(2026, 9, 21),
                last_seen=date(2026, 9, 22),
                items=[_item(ALPHA_ITEM, "alpha_signal"), _item(TLDR_ITEM, "tldr")],
            )
        ]


def _deps(monkeypatch: pytest.MonkeyPatch, mailbox_ids: list[UUID]) -> EmailAgentDeps:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda _user_id: mailbox_ids)
    return EmailAgentDeps(
        user_id=USER,
        thread_id=THREAD,
        retriever=object(),  # type: ignore[arg-type]
        news=_News(),
    )


def test_search_news_remembers_items_and_passes_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, [OWNED])

    output = execute_search_news(
        deps, "robots", since=date(2026, 9, 1), until=date(2026, 9, 30), big_only=True
    )

    assert deps.seen_ids == {TLDR_ITEM}
    assert deps.seen_passages[TLDR_ITEM].title == "Robot hands learn to fold laundry"
    assert f"[{TLDR_ITEM}]" in output
    filters = deps.news.filters  # type: ignore[attr-defined]
    assert filters.user_id == USER
    assert filters.mailbox_ids == [OWNED]
    assert filters.since == date(2026, 9, 1)
    assert filters.big_only is True


def test_list_big_news_remembers_every_item_but_not_the_story(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, [OWNED])

    output = execute_list_big_news(deps, since=date(2026, 9, 15))

    assert deps.seen_ids == {TLDR_ITEM, ALPHA_ITEM}
    assert STORY not in deps.seen_ids
    assert "alpha_signal + tldr" in output


def test_no_active_mailbox_returns_the_empty_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, [])

    assert execute_search_news(deps, "robots") == "No matching news."
    assert execute_list_big_news(deps) == "No big stories in that range."
    assert deps.seen_ids == set()

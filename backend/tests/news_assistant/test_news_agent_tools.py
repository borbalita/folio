from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.database import mailboxes
from app.news_assistant.deps import NewsAgentDeps
from app.news_assistant.tools import (
    CATCH_UP_LIMIT,
    execute_catch_up,
    execute_list_big_news,
    execute_search_news,
)
from app.retrieval.news.retriever import NewsPassage, NewsRetriever, Story

USER = UUID("00000000-0000-0000-0000-000000000001")
THREAD = UUID("00000000-0000-0000-0000-000000000002")
OWNED = UUID("00000000-0000-0000-0000-000000000010")
TLDR_ITEM = UUID("00000000-0000-0000-0000-0000000000a1")
ALPHA_ITEM = UUID("00000000-0000-0000-0000-0000000000a2")
STORY = UUID("00000000-0000-0000-0000-0000000000c1")
TODAY = date(2026, 10, 21)


def _item(item_id: UUID, source: str) -> NewsPassage:
    return NewsPassage(
        item_id=item_id,
        story_id=STORY,
        source=source,
        edition_date=date(2026, 10, 20),
        title="Lab ships a new model",
        blurb="It reasons better.",
        url="https://example.com/model",
        score=0.5,
    )


class _News(NewsRetriever):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, int | None]] = []

    def search(self, query, *, filters, session=None):  # type: ignore[override]
        self.calls.append(("search", filters, None))
        return [_item(TLDR_ITEM, "tldr")] if filters.mailbox_ids else []

    def stories(self, *, filters, limit, session=None):  # type: ignore[override]
        self.calls.append(("stories", filters, limit))
        if not filters.mailbox_ids:
            return []
        return [
            Story(
                story_id=STORY,
                first_seen=date(2026, 10, 20),
                last_seen=date(2026, 10, 20),
                is_big=True,
                sources=["alpha_signal", "tldr"],
                item_count=2,
                items=[_item(ALPHA_ITEM, "alpha_signal"), _item(TLDR_ITEM, "tldr")],
            )
        ]


def _deps(monkeypatch: pytest.MonkeyPatch, mailbox_ids: list[UUID]) -> NewsAgentDeps:
    monkeypatch.setattr(mailboxes, "news_mailbox_ids", lambda _user_id: mailbox_ids)
    monkeypatch.setattr("app.news_assistant.tools.berlin_today", lambda: TODAY)
    return NewsAgentDeps(user_id=USER, thread_id=THREAD, news=_News())


def _last_call(deps: NewsAgentDeps) -> tuple[str, object, int | None]:
    return deps.news.calls[-1]  # type: ignore[attr-defined]


@pytest.mark.parametrize("execute", [execute_list_big_news, execute_catch_up])
def test_no_dates_cover_the_seven_days_up_to_today(
    monkeypatch: pytest.MonkeyPatch, execute
) -> None:
    deps = _deps(monkeypatch, [OWNED])

    execute(deps)

    _kind, filters, _limit = _last_call(deps)
    assert (filters.since, filters.until) == (date(2026, 10, 15), TODAY)
    assert filters.user_id == USER
    assert filters.mailbox_ids == [OWNED]


def test_one_date_is_passed_on_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(monkeypatch, [OWNED])

    execute_catch_up(deps, since=date(2026, 10, 19))

    _kind, filters, _limit = _last_call(deps)
    assert (filters.since, filters.until) == (date(2026, 10, 19), None)


def test_list_big_news_reads_only_big_stories(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(monkeypatch, [OWNED])

    output = execute_list_big_news(deps)

    _kind, filters, _limit = _last_call(deps)
    assert filters.big_only is True
    assert "Big — both newsletters · 2 items · Oct 20" in output


def test_catch_up_reads_all_stories_up_to_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, [OWNED])

    execute_catch_up(deps)

    _kind, filters, limit = _last_call(deps)
    assert filters.big_only is False
    assert limit == CATCH_UP_LIMIT == 60


def test_story_items_are_remembered_but_not_the_story(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, [OWNED])

    execute_catch_up(deps)

    assert deps.seen_ids == {TLDR_ITEM, ALPHA_ITEM}
    assert STORY not in deps.seen_ids


def test_search_news_has_no_default_window(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(monkeypatch, [OWNED])

    output = execute_search_news(deps, "new model", big_only=True)

    _kind, filters, _limit = _last_call(deps)
    assert (filters.since, filters.until, filters.big_only) == (None, None, True)
    assert deps.seen_ids == {TLDR_ITEM}
    assert f"[{TLDR_ITEM}]" in output


def test_no_active_mailbox_gives_the_empty_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, [])

    assert execute_list_big_news(deps) == "No big stories in that period."
    assert execute_catch_up(deps) == "No newsletter stories in that period."
    assert execute_search_news(deps, "robots") == "No matching news."
    assert deps.seen_ids == set()

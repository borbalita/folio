import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from app.database.models.email.news_item import NewsItem
from app.database.models.email.story import NewsStory
from ingest.email.stories import (
    PlannedStory,
    demo_story_ids_query,
    is_big,
    owner_items_query,
    plan_stories,
    rebuild_stories,
    stories_to_delete,
)


def test_jev_yes_is_one_big_story() -> None:
    day = date(2026, 9, 28)
    later = day + timedelta(days=1)
    tldr = _item("tldr", day, [1.0, 0.0], "OpenAI pauses training")
    alpha = _item("alpha_signal", later, [1.0, 0.0], "OpenAI sandbox escape")

    planned, _decisions = plan_stories(
        [tldr, alpha], day, same_story=lambda _left, _right: True, window_hours=48
    )

    assert len(planned) == 1
    story = planned[0]
    assert story.is_big is True
    assert story.first_seen == day
    assert story.last_seen == later
    assert _ids(story) == {tldr.id, alpha.id}


def test_two_tldr_items_stay_separate_stories() -> None:
    day = date(2026, 9, 28)
    first = _item("tldr", day, [1.0, 0.0], "One")
    second = _item("tldr", day, [1.0, 0.0], "Two")

    planned, _decisions = plan_stories(
        [first, second],
        day,
        same_story=_not_compared,
        window_hours=48,
    )

    assert len(planned) == 2
    assert all(story.is_big is False for story in planned)
    assert _ids(planned[0]) != _ids(planned[1])
    assert _ids(planned[0]) | _ids(planned[1]) == {first.id, second.id}


def test_jev_no_stays_two_stories() -> None:
    day = date(2026, 9, 28)
    tldr = _item("tldr", day, [1.0, 0.0], "OpenAI")
    alpha = _item("alpha_signal", day, [1.0, 1.0], "A different story")

    planned, _decisions = plan_stories(
        [tldr, alpha], day, same_story=lambda _left, _right: False, window_hours=48
    )

    assert len(planned) == 2
    assert all(story.is_big is False for story in planned)
    assert {_ids(story) for story in planned} == {
        frozenset([tldr.id]),
        frozenset([alpha.id]),
    }


def test_failed_check_does_not_pair() -> None:
    day = date(2026, 9, 28)
    tldr = _item("tldr", day, [1.0, 0.0], "OpenAI")
    alpha = _item("alpha_signal", day, [1.0, 0.0], "OpenAI pause")

    planned, _decisions = plan_stories(
        [tldr, alpha], day, same_story=lambda _left, _right: None, window_hours=48
    )

    assert {_ids(story) for story in planned} == {
        frozenset([tldr.id]),
        frozenset([alpha.id]),
    }


def test_item_outside_the_window_is_not_paired() -> None:
    day = date(2026, 9, 28)
    tldr = _item("tldr", day, [1.0, 0.0], "OpenAI")
    alpha = _item(
        "alpha_signal",
        day + timedelta(days=3),
        [1.0, 0.0],
        "Same story, too early",
    )

    planned, _decisions = plan_stories(
        [tldr, alpha], day, same_story=lambda _left, _right: True, window_hours=48
    )

    assert len(planned) == 1
    assert planned[0].is_big is False
    assert _ids(planned[0]) == {tldr.id}


def test_outside_item_that_shared_a_story_becomes_its_own() -> None:
    day = date(2026, 9, 28)
    shared = uuid.uuid4()
    tldr = _item("tldr", day, [1.0, 0.0], "OpenAI")
    alpha = _item(
        "alpha_signal",
        day + timedelta(days=3),
        [1.0, 0.0],
        "Same story, too early",
    )
    tldr.story_id = shared
    alpha.story_id = shared

    planned, _decisions = plan_stories(
        [tldr, alpha], day, same_story=_not_compared, window_hours=48
    )

    assert len(planned) == 2
    assert {_ids(story) for story in planned} == {
        frozenset([tldr.id]),
        frozenset([alpha.id]),
    }
    assert all(story.is_big is False for story in planned)


def _item(source: str, edition: date, embedding: list[float], title: str) -> NewsItem:
    return NewsItem(
        id=uuid.uuid4(),
        email_id=uuid.uuid4(),
        source=source,
        edition_date=edition,
        position=0,
        title=title,
        blurb="A sentence.",
        url="https://example.com",
        embedding=embedding,
        embedding_model="test",
        embedding_dimensions=len(embedding),
    )


def _not_compared(_left: NewsItem, _right: NewsItem) -> bool:
    raise AssertionError("same source or an item outside the window was compared")


def _ids(story: PlannedStory) -> frozenset[uuid.UUID]:
    return frozenset(item.id for item in story.items)


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        (["tldr", "alpha_signal"], True),
        (["demo_tensor", "demo_detective"], True),
        (["tldr", "demo_detective"], False),
        (["demo_tensor", "alpha_signal"], False),
        (["tldr"], False),
        (["demo_tensor", "demo_tensor"], False),
    ],
)
def test_big_means_both_newsletters_of_one_pair(
    sources: list[str], expected: bool
) -> None:
    items = [_item(s, date(2026, 9, 28), [1.0, 0.0], "A story") for s in sources]

    assert is_big(items) is expected


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_owner_item_query_excludes_demo_mailboxes() -> None:
    sql = _sql(owner_items_query())

    assert "JOIN emails ON emails.id = news_items.email_id" in sql
    assert "JOIN mailboxes ON mailboxes.id = emails.mailbox_id" in sql
    assert "mailboxes.provider != 'demo'" in sql


def test_demo_story_query_selects_only_demo_items() -> None:
    sql = _sql(demo_story_ids_query())

    assert "mailboxes.provider = 'demo'" in sql
    assert "news_items.story_id IS NOT NULL" in sql


def test_story_referenced_only_by_demo_items_survives() -> None:
    owner, demo, orphan, replaced = (uuid.uuid4() for _ in range(4))

    doomed = stories_to_delete(
        [owner, demo, orphan, replaced],
        replaced={replaced},
        referenced={owner, replaced},
        demo_referenced={demo},
    )

    assert doomed == {orphan, replaced}


class _FakeSession:
    """Answers each statement by its compiled SQL and records deletes."""

    def __init__(self, owner_items, demo_story_ids, stories) -> None:
        self.owner_items = owner_items
        self.demo_story_ids = demo_story_ids
        self.stories = stories
        self.statements: list[str] = []
        self.deleted: list[NewsStory] = []
        self.added: list[NewsStory] = []

    def scalars(self, statement):
        sql = _sql(statement)
        self.statements.append(sql)
        if "mailboxes.provider != 'demo'" in sql:
            return list(self.owner_items)
        if "mailboxes.provider = 'demo'" in sql:
            return list(self.demo_story_ids)
        return list(self.stories)

    def delete(self, story) -> None:
        self.deleted.append(story)

    def add(self, story) -> None:
        story.id = uuid.uuid4()
        self.added.append(story)

    def flush(self) -> None:
        pass


def test_rebuild_stories_never_touches_demo_stories() -> None:
    day = date(2026, 9, 28)
    demo_story = NewsStory(id=uuid.uuid4(), first_seen=day, last_seen=day, is_big=True)
    orphan = NewsStory(id=uuid.uuid4(), first_seen=day, last_seen=day, is_big=False)
    old = NewsStory(id=uuid.uuid4(), first_seen=day, last_seen=day, is_big=False)
    tldr = _item("tldr", day, [1.0, 0.0], "Owner news")
    tldr.story_id = old.id
    session = _FakeSession([tldr], [demo_story.id], [demo_story, orphan, old])

    count = rebuild_stories(session, day, same_story=lambda _l, _r: True)  # type: ignore[arg-type]

    assert "mailboxes.provider != 'demo'" in session.statements[0]
    assert demo_story not in session.deleted
    assert set(map(id, session.deleted)) == {id(orphan), id(old)}
    assert count == 1
    assert tldr.story_id == session.added[0].id


def test_rebuild_stories_reads_stories_before_demo_story_ids() -> None:
    day = date(2026, 9, 28)
    session = _FakeSession([], [], [])

    rebuild_stories(session, day, same_story=lambda _l, _r: True)  # type: ignore[arg-type]

    kinds = [
        "demo" if "mailboxes.provider = 'demo'" in sql else "other"
        for sql in session.statements
        if "mailboxes.provider != 'demo'" not in sql
    ]
    assert kinds == ["other", "demo"]

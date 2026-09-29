import uuid
from datetime import date, timedelta

from app.database.models.email.news_item import NewsItem
from ingest.email.stories import PlannedStory, plan_stories


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
    assert {_ids(story) for story in planned} == {frozenset([tldr.id]), frozenset([alpha.id])}


def test_failed_check_does_not_pair() -> None:
    day = date(2026, 9, 28)
    tldr = _item("tldr", day, [1.0, 0.0], "OpenAI")
    alpha = _item("alpha_signal", day, [1.0, 0.0], "OpenAI pause")

    planned, _decisions = plan_stories(
        [tldr, alpha], day, same_story=lambda _left, _right: None, window_hours=48
    )

    assert {_ids(story) for story in planned} == {frozenset([tldr.id]), frozenset([alpha.id])}


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
    assert {_ids(story) for story in planned} == {frozenset([tldr.id]), frozenset([alpha.id])}
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

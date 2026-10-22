import uuid
from collections import Counter
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.database.models.email.message import EmailLabel
from app.demo.accounts import DemoAccounts
from app.demo.news_fixture import load_fixture
from app.demo.news_state import build_news_rows

TODAY = date(2026, 10, 21)
ACCOUNTS = DemoAccounts(mailbox_id=uuid.uuid4(), account_id=uuid.uuid4())
TO = "demo+1@folio.example"
FIXTURE = load_fixture()


def _build(today: date = TODAY):
    return build_news_rows(today, ACCOUNTS, to_address=TO)


def test_the_real_fixture_has_vectors_of_the_configured_size() -> None:
    assert len(FIXTURE) == 37
    assert all(
        len(item.embedding) == settings.openai_embedding_dimensions for item in FIXTURE
    )


def test_one_email_per_newsletter_per_day() -> None:
    rows = _build()
    editions = {(i.source, i.days_ago) for i in FIXTURE}

    assert len(rows.emails) == len(editions)
    assert len({(e.newsletter_source, e.sent_at.date()) for e in rows.emails}) == len(
        editions
    )
    assert len(rows.items) == len(FIXTURE)
    for email in rows.emails:
        assert email.label == EmailLabel.AI_NEWSLETTER
        assert email.mailbox_id == ACCOUNTS.mailbox_id
        assert email.from_address.endswith(".example")
        assert email.to_addresses == [TO]
        assert email.sent_at.hour == 7
        assert email.sent_at.tzinfo == ZoneInfo(settings.email_timezone)
        assert email.embedding_model == settings.openai_embedding_model


def test_subjects_follow_the_newsletter() -> None:
    rows = _build()
    tensor = [e for e in rows.emails if e.newsletter_source == "demo_tensor"]
    detective = [e for e in rows.emails if e.newsletter_source == "demo_detective"]

    assert {e.from_name for e in tensor} == {"The Daily Tensor"}
    assert {e.from_name for e in detective} == {"AI Detective"}
    assert all(
        e.subject == f"The Daily Tensor — {e.sent_at.date().isoformat()}"
        for e in tensor
    )
    assert all(e.subject.startswith("AI Detective #") for e in detective)
    assert len({e.subject for e in detective}) == len(detective)


def test_the_body_lists_the_days_items() -> None:
    rows = _build()
    by_id = {e.id: e for e in rows.emails}

    for item in rows.items:
        body = by_id[item.email_id].body
        assert item.title in body
        assert item.blurb in body
        assert item.url in body


def test_items_carry_fixture_vectors_and_dates_from_the_email() -> None:
    rows = _build()
    by_id = {e.id: e for e in rows.emails}
    vectors = {item.title: item.embedding for item in FIXTURE}

    for item in rows.items:
        assert item.embedding == vectors[item.title]
        assert item.edition_date == by_id[item.email_id].sent_at.date()
        assert item.source == by_id[item.email_id].newsletter_source
        assert item.embedding_dimensions == settings.openai_embedding_dimensions
    positions = Counter((i.email_id, i.position) for i in rows.items)
    assert max(positions.values()) == 1


def test_every_item_has_a_story_in_the_build() -> None:
    rows = _build()
    story_ids = {s.id for s in rows.stories}

    assert all(item.story_id in story_ids for item in rows.items)
    assert len(rows.stories) == len({i.story for i in FIXTURE})
    assert {s.id for s in rows.stories} == {i.story_id for i in rows.items}


def test_stories_span_their_items_and_big_means_both_newsletters() -> None:
    rows = _build()
    members: dict[uuid.UUID, list] = {}
    for item in rows.items:
        members.setdefault(item.story_id, []).append(item)

    assert any(s.is_big for s in rows.stories)
    assert any(not s.is_big for s in rows.stories)
    for story in rows.stories:
        items = members[story.id]
        assert story.first_seen == min(i.edition_date for i in items)
        assert story.last_seen == max(i.edition_date for i in items)
        assert story.is_big == (len({i.source for i in items}) == 2)


@pytest.mark.parametrize("today", [date(2026, 1, 31), date(2028, 2, 29)])
def test_dates_move_with_today(today: date) -> None:
    rows = _build(today)
    days_ago = {i.days_ago for i in FIXTURE}

    assert {i.edition_date for i in rows.items} == {
        today - timedelta(days=n) for n in days_ago
    }


def test_each_build_has_fresh_ids() -> None:
    first, second = _build(), _build()

    assert not {e.message_id for e in first.emails} & {
        e.message_id for e in second.emails
    }
    assert not {s.id for s in first.stories} & {s.id for s in second.stories}

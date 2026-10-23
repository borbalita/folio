import calendar
import json
import re
import uuid
from datetime import date

import pytest

from app.config import settings
from app.demo import embed_mail_fixture
from app.demo.accounts import DemoAccounts
from app.demo.mail_dates import appointment_dates
from app.demo.mail_fixture import DRAFT_PATH, load_fixture
from app.demo.mail_state import build_mail_rows

ACCOUNTS = DemoAccounts(
    mailbox_id=uuid.uuid4(),
    account_id=uuid.uuid4(),
    card_account_id=uuid.uuid4(),
    wallet_account_id=uuid.uuid4(),
)
TO = "demo@tasnadi-ai.example"


def _fixture(tmp_path_factory: pytest.TempPathFactory):
    # The real mail_fixture.json needs one OpenAI run; tests use the draft with dummy vectors.
    output = embed_mail_fixture.build_output(
        json.loads(DRAFT_PATH.read_text()),
        lambda texts: [[0.25] * settings.openai_embedding_dimensions for _ in texts],
        lambda text: 42,
    )
    path = tmp_path_factory.mktemp("mail") / "mail_fixture.json"
    path.write_text(json.dumps(output))
    return load_fixture(path)


@pytest.fixture(scope="module")
def fixture(tmp_path_factory: pytest.TempPathFactory):
    return _fixture(tmp_path_factory)


PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::short)?\}")


def _days(year: int, month: int) -> list[date]:
    return [
        date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)
    ]


def test_every_fixture_email_becomes_one_email_and_one_chunk(fixture) -> None:
    _, MAILS = fixture
    rows = build_mail_rows(date(2026, 10, 23), ACCOUNTS, to_address=TO, fixture=fixture)

    assert len(rows.emails) == len(MAILS) == 40
    assert len(rows.chunks) == 40
    by_id = {email.id: email for email in rows.emails}
    assert all(chunk.email_id in by_id for chunk in rows.chunks)
    assert all(chunk.chunk_index == 0 for chunk in rows.chunks)
    assert all(chunk.token_count == 42 for chunk in rows.chunks)
    assert all(
        len(chunk.embedding) == settings.openai_embedding_dimensions
        for chunk in rows.chunks
    )
    assert {e.label for e in rows.emails} == {m.label for m in MAILS}
    assert all(e.mailbox_id == ACCOUNTS.mailbox_id for e in rows.emails)
    assert all(e.to_addresses == [TO] for e in rows.emails)


def test_placeholders_are_filled_for_the_reset_day(fixture) -> None:
    RULES, _ = fixture
    today = date(2026, 11, 3)
    rows = build_mail_rows(today, ACCOUNTS, to_address=TO, fixture=fixture)
    dentist = appointment_dates(RULES, today)["dentist"]

    texts = [e.subject + e.body for e in rows.emails] + [
        c.chunk_text for c in rows.chunks
    ]
    assert not any(PLACEHOLDER.search(text) for text in texts)
    reminder = next(e for e in rows.emails if e.from_name.startswith("Zahnarztpraxis"))
    assert f"{dentist:%d.%m.}" in reminder.subject
    assert "November 2026" in reminder.body


@pytest.mark.parametrize("today", _days(2026, 10) + _days(2027, 2))
def test_mail_is_sent_before_its_appointments_and_never_in_the_future(
    today: date, fixture
) -> None:
    RULES, MAILS = fixture
    rows = build_mail_rows(today, ACCOUNTS, to_address=TO, fixture=fixture)
    dates = appointment_dates(RULES, today)
    by_key = dict(zip((m.key for m in MAILS), rows.emails, strict=True))

    for mail in MAILS:
        email = by_key[mail.key]
        assert email.sent_at.date() <= today, mail.key
        for name in set(PLACEHOLDER.findall(mail.subject + mail.body)):
            assert email.sent_at < dates[name], (mail.key, name)


def test_two_builds_have_fresh_message_ids(fixture) -> None:
    first = build_mail_rows(
        date(2026, 10, 23), ACCOUNTS, to_address=TO, fixture=fixture
    )
    second = build_mail_rows(
        date(2026, 10, 23), ACCOUNTS, to_address=TO, fixture=fixture
    )

    assert not {e.message_id for e in first.emails} & {
        e.message_id for e in second.emails
    }

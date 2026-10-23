import calendar
import json
import re
from datetime import date

import pytest

from app.config import settings
from app.demo import embed_mail_fixture
from app.demo.mail_dates import appointment_dates
from app.demo.mail_fixture import DRAFT_PATH, REFERENCE_DAY, load_draft, load_fixture

LABELS = {"needs_reply", "promotional", "newsletter", "other"}
RULES, MAILS = load_draft()
DOCTORS = re.compile(r"Praxis|praxis|Doctolino|Physiotherapie", re.IGNORECASE)


def test_draft_has_forty_everyday_emails() -> None:
    assert len(MAILS) == 40
    assert len({mail.key for mail in MAILS}) == 40
    assert all(mail.from_address.endswith(".example") for mail in MAILS)
    assert {mail.label for mail in MAILS} <= LABELS
    assert sum(mail.label == "needs_reply" for mail in MAILS) >= 2


def test_doctors_and_the_distractors_are_there() -> None:
    doctor_mails = [mail for mail in MAILS if DOCTORS.search(mail.from_name)]
    assert len(doctor_mails) >= 6
    assert {"dentist", "gp", "eyes", "physio_old", "physio_new", "derma"} <= set(RULES)
    assert RULES["derma"].month == "next"
    assert "buergeramt" in RULES  # an appointment this month that isn't a doctor's


def test_every_placeholder_has_a_rule() -> None:
    for mail in MAILS:
        for name in re.findall(r"\{([a-z_]+)(?::short)?\}", mail.subject + mail.body):
            assert name in RULES, (mail.key, name)


def _days(year: int, month: int) -> list[date]:
    return [
        date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)
    ]


@pytest.mark.parametrize(
    "today", [d for m in ((2026, 10), (2026, 11), (2027, 2)) for d in _days(*m)][::7]
)
def test_fixture_appointments_are_distinct_days(today: date) -> None:
    dates = appointment_dates(RULES, today)

    assert len({when.date() for when in dates.values()}) == len(dates)
    assert dates["physio_old"] < dates["physio_new"]


def test_script_renders_for_the_reference_day_and_keeps_token_counts() -> None:
    texts: list[str] = []

    def fake_embed(batch: list[str]) -> list[list[float]]:
        texts.extend(batch)
        return [[0.5] * settings.openai_embedding_dimensions for _ in batch]

    output = embed_mail_fixture.build_output(
        json.loads(DRAFT_PATH.read_text()), fake_embed, lambda text: 7
    )

    assert len(texts) == 40
    assert not any(
        "{" in text and "}" in text and re.search(r"\{[a-z_]+(:short)?\}", text)
        for text in texts
    )
    dentist = appointment_dates(RULES, REFERENCE_DAY)["dentist"]
    assert any(f"{dentist:%d.%m.}" in text for text in texts)
    assert all(mail["token_count"] == 7 for mail in output["emails"])
    assert output["embedding_model"] == settings.openai_embedding_model


def test_loader_refuses_another_embedding_model(tmp_path) -> None:
    path = tmp_path / "mail.json"
    path.write_text(
        json.dumps(
            {
                "embedding_model": "other",
                "embedding_dimensions": 3,
                "appointments": {},
                "emails": [],
            }
        )
    )

    with pytest.raises(ValueError, match="embedding"):
        load_fixture(path)

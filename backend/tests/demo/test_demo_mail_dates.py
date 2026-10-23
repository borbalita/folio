import calendar
from datetime import date, datetime

import pytest

from app.demo.mail_dates import AppointmentRule, appointment_dates, render

RULES = {
    "dentist": AppointmentRule(month="this", slot=0.15, time="09:30"),
    "gp": AppointmentRule(month="this", slot=0.4, time="08:15"),
    "physio_old": AppointmentRule(month="this", slot=0.3, time="17:00"),
    "physio_new": AppointmentRule(month="this", slot=0.75, time="17:00"),
    "eyes": AppointmentRule(month="this", slot=0.9, time="14:45"),
    "derma": AppointmentRule(month="next", slot=0.2, time="11:00"),
}


def _days(year: int, month: int) -> list[date]:
    return [
        date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)
    ]


@pytest.mark.parametrize("today", _days(2026, 10) + _days(2026, 11) + _days(2027, 2))
def test_appointments_fall_in_the_right_month_on_weekdays(today: date) -> None:
    dates = appointment_dates(RULES, today)
    following = (today.month % 12 + 1, today.year + (today.month == 12))

    for name, rule in RULES.items():
        when = dates[name]
        assert when.weekday() < 5, name
        if rule.month == "this":
            assert (when.year, when.month) == (today.year, today.month), name
        else:
            assert (when.month, when.year) == following, name
    assert len({d.date() for d in dates.values()}) == len(dates)
    assert dates["physio_old"] < dates["physio_new"]


def test_times_are_local() -> None:
    when = appointment_dates(RULES, date(2026, 10, 23))["dentist"]

    assert (when.hour, when.minute) == (9, 30)
    assert when.tzinfo is not None and when.utcoffset() is not None


def test_render_fills_long_and_short_german_dates() -> None:
    dates = {"dentist": datetime(2026, 10, 6, 9, 30)}

    text = render("Ihr Termin am {dentist} (Kurz: {dentist:short})", dates)

    assert text == "Ihr Termin am Dienstag, 6. Oktober 2026, 09:30 Uhr (Kurz: 06.10.)"


def test_render_leaves_text_without_placeholders_alone() -> None:
    assert render("Hallo {name nicht}", {}) == "Hallo {name nicht}"

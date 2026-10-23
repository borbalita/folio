"""Appointment dates for the demo mail, placed in the reset day's month or the next.

The demo question is "Do I have any doctor's appointments this month?", so the dates can't be
plain offsets from today: on the 30th they would spill into the next month.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from app.config import settings

WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)
MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip
_PLACEHOLDER = re.compile(r"\{([a-z_]+)(:short)?\}")


@dataclass(frozen=True, slots=True)
class AppointmentRule:
    month: Literal["this", "next"]
    # Where in the month, 0.0 = the 1st, 1.0 = the last day.
    slot: float
    time: str


def _weekday_in_month(year: int, month: int, slot: float, taken: set[date]) -> date:
    """The weekday nearest the slot that no other appointment uses, inside the month."""
    last = calendar.monthrange(year, month)[1]
    target = date(year, month, 1 + round(slot * (last - 1)))
    candidates = [date(year, month, day) for day in range(1, last + 1)]
    free = [day for day in candidates if day.weekday() < 5 and day not in taken]
    # Nearest first; on a tie the later day, so "moved" appointments keep moving forward.
    return min(free, key=lambda day: (abs((day - target).days), target - day))


def appointment_dates(
    rules: dict[str, AppointmentRule], today: date
) -> dict[str, datetime]:
    zone = ZoneInfo(settings.email_timezone)
    next_year, next_month = (
        (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    )
    dates = {}
    taken: set[date] = set()
    for name, rule in rules.items():
        year, month = (
            (today.year, today.month)
            if rule.month == "this"
            else (next_year, next_month)
        )
        hour, minute = (int(part) for part in rule.time.split(":"))
        day = _weekday_in_month(year, month, rule.slot, taken)
        taken.add(day)
        dates[name] = datetime.combine(day, time(hour, minute), tzinfo=zone)
    return dates


def long_date(when: datetime) -> str:
    return (
        f"{WEEKDAYS[when.weekday()]}, {when.day}. {MONTHS[when.month - 1]} {when.year}, "
        f"{when:%H:%M} Uhr"
    )


def render(text: str, dates: dict[str, datetime]) -> str:
    """Fill {name} with the long German date and {name:short} with dd.mm.; unknown names stay."""

    def fill(match: re.Match[str]) -> str:
        when = dates.get(match.group(1))
        if when is None:
            return match.group(0)
        return f"{when:%d.%m.}" if match.group(2) else long_date(when)

    return _PLACEHOLDER.sub(fill, text)

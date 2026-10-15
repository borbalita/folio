"""When bank access needs renewing, and which warning email is due."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

Status = Literal["active", "expiring", "expired"]

EXPIRING_WITHIN = timedelta(days=14)
# Ordered: a later stage supersedes an earlier one.
STAGES: tuple[tuple[str, timedelta], ...] = (
    ("14d", timedelta(days=14)),
    ("3d", timedelta(days=3)),
    ("expired", timedelta(0)),
)


def connection_status(
    valid_until: datetime | None, invalidated_at: datetime | None, now: datetime
) -> Status:
    if invalidated_at is not None or valid_until is None or valid_until <= now:
        return "expired"
    if valid_until - now <= EXPIRING_WITHIN:
        return "expiring"
    return "active"


def due_notice(
    valid_until: datetime | None,
    invalidated_at: datetime | None,
    sent: str | None,
    now: datetime,
) -> str | None:
    """The highest stage reached and not yet sent; earlier skipped stages are not sent.

    "At or below" rather than "exactly at", so a sync every few hours never misses one.
    """
    if connection_status(valid_until, invalidated_at, now) == "expired":
        due = "expired"
    else:
        assert valid_until is not None
        left = valid_until - now
        reached = [stage for stage, at in STAGES[:-1] if left <= at]
        if not reached:
            return None
        due = reached[-1]
    order = [stage for stage, _ in STAGES]
    if sent is not None and order.index(sent) >= order.index(due):
        return None
    return due

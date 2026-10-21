from datetime import UTC, datetime, timedelta

from app.finance.expiry import connection_status, due_notice

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def days(n: float) -> datetime:
    return NOW + timedelta(days=n)


def test_status_active_expiring_expired() -> None:
    assert connection_status(days(15), None, NOW) == "active"
    assert connection_status(days(14), None, NOW) == "expiring"
    assert connection_status(days(0), None, NOW) == "expired"
    assert connection_status(days(-1), None, NOW) == "expired"
    assert connection_status(days(100), NOW, NOW) == "expired"
    assert connection_status(None, None, NOW) == "expired"


def test_due_notice_at_13_days_then_nothing() -> None:
    assert due_notice(days(13), None, None, NOW) == "14d"
    assert due_notice(days(13), None, "14d", NOW) is None
    assert due_notice(days(20), None, None, NOW) is None


def test_due_notice_between_runs_still_sends() -> None:
    assert due_notice(days(13.6), None, None, NOW) == "14d"


def test_due_notice_skips_to_highest_stage() -> None:
    assert due_notice(days(2), None, None, NOW) == "3d"
    assert due_notice(days(2), None, "14d", NOW) == "3d"
    assert due_notice(days(2), None, "3d", NOW) is None


def test_due_notice_expired_after_3d() -> None:
    assert due_notice(days(-0.1), None, "3d", NOW) == "expired"
    assert due_notice(days(90), NOW, None, NOW) == "expired"
    assert due_notice(days(-1), None, "expired", NOW) is None

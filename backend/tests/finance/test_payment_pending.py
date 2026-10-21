from datetime import UTC, datetime, timedelta

import pytest

from app.database.payments import PENDING_DAYS, is_payment_pending

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


def test_pending_lasts_five_days() -> None:
    assert PENDING_DAYS == 5


@pytest.mark.parametrize(
    ("status", "approved_at", "pending"),
    [
        ("approved", NOW - timedelta(hours=1), True),
        ("approved", NOW - timedelta(days=PENDING_DAYS) + timedelta(minutes=1), True),
        # No matching debit for 5 days: the invoice shows open again.
        ("approved", NOW - timedelta(days=PENDING_DAYS, minutes=1), False),
        ("approved", None, False),
        ("draft", NOW - timedelta(hours=1), False),
        ("completed", NOW - timedelta(hours=1), False),
        ("cancelled", NOW - timedelta(hours=1), False),
    ],
)
def test_only_a_recent_approved_payment_is_pending(
    status: str, approved_at: datetime | None, pending: bool
) -> None:
    assert is_payment_pending(status, approved_at, NOW) is pending


def test_pending_ids_keep_only_invoices_with_a_recent_approved_payment() -> None:
    import uuid
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.database.payments import pending_invoice_ids

    recent, stale, done = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(invoice_id=recent, status="approved", approved_at=NOW - timedelta(days=1)),
        SimpleNamespace(invoice_id=stale, status="approved", approved_at=NOW - timedelta(days=9)),
        SimpleNamespace(invoice_id=done, status="completed", approved_at=NOW - timedelta(days=1)),
    ]

    assert pending_invoice_ids(session, [recent, stale, done], now=NOW) == {recent}
    assert pending_invoice_ids(session, [], now=NOW) == set()

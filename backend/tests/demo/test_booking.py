from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.database.matches import _debit
from app.database.models.finance.payment_draft import PaymentDraft
from app.demo import booking
from app.demo.booking import booking_transaction
from app.finance.matching import InvoiceFacts, propose

USER = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
ACCOUNT = uuid.UUID("00000000-0000-0000-0000-0000000000d2")
INVOICE = uuid.UUID("00000000-0000-0000-0000-0000000000d3")
IBAN = "DE89370400440532013000"
TODAY = date(2026, 10, 21)


def _draft(status: str = "approved") -> PaymentDraft:
    return PaymentDraft(
        id=uuid.uuid4(),
        invoice_id=INVOICE,
        payee="Stadtwerke Lindenstrom",
        iban=IBAN,
        amount=Decimal("42.50"),
        currency="EUR",
        reference="R-1001",
        status=status,
    )


def test_the_booking_is_a_strong_match_for_its_invoice() -> None:
    draft = _draft()
    tx = booking_transaction(draft, ACCOUNT, TODAY)
    tx.id = uuid.uuid4()
    invoice = InvoiceFacts(
        id=INVOICE,
        amount=Decimal("42.50"),
        currency="EUR",
        iban=IBAN,
        invoice_number="R-1001",
        reference=None,
        payee="Stadtwerke Lindenstrom",
        start=date(2026, 10, 1),
    )

    [proposal] = propose(invoice, [_debit(tx)], rejected=set(), taken=set())

    assert proposal.status == "linked"
    assert "iban" in proposal.signals
    assert tx.account_id == ACCOUNT
    assert tx.amount == Decimal("-42.50")
    assert tx.booking_date == TODAY
    assert tx.dedup_key == f"demo-booking:{draft.id}"


class _Insert:
    def __init__(self, inserted: bool) -> None:
        self.inserted = inserted

    def scalar_one_or_none(self) -> uuid.UUID | None:
        return uuid.uuid4() if self.inserted else None


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    draft: PaymentDraft | None,
    *,
    inserted: bool = True,
) -> tuple[MagicMock, list[uuid.UUID]]:
    session = MagicMock()
    session.scalar.return_value = draft
    session.execute.return_value = _Insert(inserted)
    matched: list[uuid.UUID] = []

    @contextmanager
    def fake_session():
        yield session

    def match(user_id: uuid.UUID) -> dict[str, int]:
        matched.append(user_id)
        if draft is not None:
            draft.status = "completed"
        return {"linked": 1, "suggested": 0}

    monkeypatch.setattr(booking, "get_session", fake_session)
    monkeypatch.setattr(booking, "match_for_user", match)
    monkeypatch.setattr(
        booking,
        "ensure_demo_accounts",
        lambda _session, _user_id: SimpleNamespace(account_id=ACCOUNT),
    )
    monkeypatch.setattr(booking, "_statuses", lambda _draft_id: ("completed", "paid"))
    return session, matched


def test_booking_an_approved_payment_inserts_once_and_runs_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _draft()
    session, matched = _patch(monkeypatch, draft)

    result = booking.book(USER, draft.id, today=TODAY)

    assert result == {
        "booked": True,
        "paymentStatus": "completed",
        "invoiceStatus": "paid",
    }
    assert session.execute.call_count == 1
    session.commit.assert_called_once()
    assert matched == [USER]


def test_a_payment_already_booked_and_matched_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _draft(status="completed")
    session, matched = _patch(monkeypatch, draft)

    result = booking.book(USER, draft.id, today=TODAY)

    assert result == {
        "booked": False,
        "paymentStatus": "completed",
        "invoiceStatus": "paid",
    }
    session.execute.assert_not_called()
    session.commit.assert_not_called()
    assert matched == []


def test_a_second_booking_before_matching_adds_no_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _draft()
    session, matched = _patch(monkeypatch, draft, inserted=False)

    result = booking.book(USER, draft.id, today=TODAY)

    assert result["booked"] is False
    session.commit.assert_not_called()
    assert matched == []


def test_another_users_payment_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session, matched = _patch(monkeypatch, None)

    with pytest.raises(HTTPException) as caught:
        booking.book(USER, uuid.uuid4(), today=TODAY)

    assert caught.value.status_code == 404
    session.execute.assert_not_called()
    assert matched == []


def test_the_draft_query_is_scoped_to_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    session, _matched = _patch(monkeypatch, None)

    with pytest.raises(HTTPException):
        booking.book(USER, uuid.uuid4(), today=TODAY)

    statement = session.scalar.call_args.args[0]
    compiled = statement.compile()
    assert "mailboxes.user_id" in str(compiled)
    assert USER in compiled.params.values()

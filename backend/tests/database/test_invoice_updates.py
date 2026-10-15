from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.database import invoices
from app.database.models.finance.invoice import Invoice

OWN = uuid.UUID("00000000-0000-0000-0000-000000000010")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000020")
VALID_IBAN = "DE89370400440532013000"


def _row(**overrides: object) -> Invoice:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "email_id": uuid.uuid4(),
        "position": 0,
        "payee": "Stadtwerke",
        "currency": "EUR",
        "status": "needs_info",
        "issues": ["missing_iban", "missing_amount"],
        "edited_fields": [],
    }
    values.update(overrides)
    return Invoice(**values)  # type: ignore[arg-type]


def _session(rows: list[tuple[Invoice, uuid.UUID]]) -> MagicMock:
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(Invoice=row, mailbox_id=mailbox) for row, mailbox in rows
    ]
    return session


def _patch(monkeypatch: pytest.MonkeyPatch, session: MagicMock) -> None:
    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(invoices, "get_session", fake_get_session)


def test_update_rechecks_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row()
    session = _session([(row, OWN)])
    _patch(monkeypatch, session)

    result = invoices.update_invoice(
        row.id, {"iban": VALID_IBAN, "amount": Decimal(5)}, [OWN]
    )

    assert row.status == "open"
    assert result["status"] == "open"
    assert result["amount"] == "5.00"
    session.commit.assert_called_once()


def test_update_of_a_foreign_invoice_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row()
    session = _session([(row, OTHER)])
    _patch(monkeypatch, session)

    with pytest.raises(HTTPException) as caught:
        invoices.update_invoice(row.id, {"payee": "X"}, [OWN])

    assert caught.value.status_code == 403
    assert row.payee == "Stadtwerke"
    session.commit.assert_not_called()


def test_update_of_an_unknown_invoice_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, _session([]))

    with pytest.raises(HTTPException) as caught:
        invoices.update_invoice(uuid.uuid4(), {"payee": "X"}, [OWN])

    assert caught.value.status_code == 404


def test_two_invoices_are_marked_paid_and_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    open_row = _row(iban=VALID_IBAN, amount=Decimal(5), status="open", issues=[])
    needs_info = _row()
    session = _session([(open_row, OWN), (needs_info, OWN)])
    _patch(monkeypatch, session)
    ids = [open_row.id, needs_info.id]

    paid = invoices.set_invoices_paid(ids, True, [OWN])

    assert [item["status"] for item in paid] == ["paid", "paid"]
    assert [item["paidBy"] for item in paid] == ["owner", "owner"]

    unpaid = invoices.set_invoices_paid(ids, False, [OWN])

    assert [item["status"] for item in unpaid] == ["open", "needs_info"]
    assert session.commit.call_count == 2


def test_paid_with_one_foreign_invoice_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mine, theirs = _row(), _row()
    session = _session([(mine, OWN), (theirs, OTHER)])
    _patch(monkeypatch, session)

    with pytest.raises(HTTPException) as caught:
        invoices.set_invoices_paid([mine.id, theirs.id], True, [OWN])

    assert caught.value.status_code == 403
    assert mine.status == "needs_info"
    session.commit.assert_not_called()


def test_paid_with_an_unknown_id_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mine = _row()
    _patch(monkeypatch, _session([(mine, OWN)]))

    with pytest.raises(HTTPException) as caught:
        invoices.set_invoices_paid([mine.id, uuid.uuid4()], True, [OWN])

    assert caught.value.status_code == 404
    assert mine.status == "needs_info"

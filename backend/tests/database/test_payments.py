import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.database import payments
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.invoice import Invoice
from app.database.models.finance.payment_draft import PaymentDraft

OWN = uuid.UUID("00000000-0000-0000-0000-000000000010")
USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
IBAN = "DE89370400440532013000"


def _invoice(**overrides: object) -> Invoice:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "email_id": uuid.uuid4(),
        "position": 0,
        "payee": "Stadtwerke",
        "iban": IBAN,
        "amount": Decimal("49.90"),
        "currency": "EUR",
        "invoice_number": "RE-1",
        "status": "open",
        "issues": [],
        "edited_fields": [],
    }
    values.update(overrides)
    return Invoice(**values)  # type: ignore[arg-type]


ACCOUNT = BankAccount(id=uuid.uuid4(), iban="DE02120300000000202051", name="Main")


def _patch(monkeypatch: pytest.MonkeyPatch, session: MagicMock) -> None:
    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(payments, "get_session", fake_get_session)


def _sql(statement) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_a_new_draft_replaces_the_invoices_open_one(monkeypatch) -> None:
    invoice = _invoice()
    session = MagicMock()
    account = MagicMock()
    account.one_or_none.return_value = SimpleNamespace(BankAccount=ACCOUNT, bank="N26")
    rows = MagicMock()
    rows.all.return_value = [SimpleNamespace(Invoice=invoice, mailbox_id=OWN)]
    session.execute.side_effect = [account, rows, MagicMock()]
    _patch(monkeypatch, session)

    result = payments.create_drafts([invoice.id], ACCOUNT.id, USER, [OWN])

    cancel = _sql(session.execute.call_args_list[2].args[0])
    assert cancel.startswith("UPDATE payment_drafts SET status='cancelled'")
    assert str(invoice.id) in cancel
    assert "status IN ('draft', 'approved')" in cancel
    [added] = [call.args[0] for call in session.add.call_args_list]
    assert isinstance(added, PaymentDraft)
    assert (added.status, added.amount, added.reference) == ("draft", Decimal("49.90"), "RE-1")
    assert result["skipped"] == []
    session.commit.assert_called_once()


def test_paid_and_needs_info_invoices_are_skipped(monkeypatch) -> None:
    paid, needs_info = _invoice(status="paid"), _invoice(status="needs_info")
    session = MagicMock()
    account = MagicMock()
    account.one_or_none.return_value = SimpleNamespace(BankAccount=ACCOUNT, bank="N26")
    rows = MagicMock()
    rows.all.return_value = [
        SimpleNamespace(Invoice=paid, mailbox_id=OWN),
        SimpleNamespace(Invoice=needs_info, mailbox_id=OWN),
    ]
    session.execute.side_effect = [account, rows]
    _patch(monkeypatch, session)

    result = payments.create_drafts([paid.id, needs_info.id], ACCOUNT.id, USER, [OWN])

    assert result == {
        "drafts": [],
        "skipped": [
            {"invoiceId": str(paid.id), "reason": "not_open"},
            {"invoiceId": str(needs_info.id), "reason": "not_open"},
        ],
    }
    session.add.assert_not_called()


def test_account_without_iban_cannot_pay(monkeypatch) -> None:
    session = MagicMock()
    paypal = BankAccount(id=uuid.uuid4(), iban=None, name="PayPal")
    session.execute.return_value.one_or_none.return_value = SimpleNamespace(
        BankAccount=paypal, bank="PayPal"
    )
    _patch(monkeypatch, session)

    with pytest.raises(HTTPException) as exc:
        payments.create_drafts([uuid.uuid4()], paypal.id, USER, [OWN])

    assert exc.value.status_code == 400


def _draft_row(invoice: Invoice) -> SimpleNamespace:
    draft = PaymentDraft(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        account_id=ACCOUNT.id,
        payee="Stadtwerke",
        iban=IBAN,
        bic=None,
        amount=Decimal("49.90"),
        currency="EUR",
        reference="RE-1",
        status="draft",
    )
    return SimpleNamespace(
        PaymentDraft=draft, Invoice=invoice, BankAccount=ACCOUNT, bank="N26", mailbox_id=OWN
    )


def test_approve_is_refused_when_the_invoice_was_paid_meanwhile(monkeypatch) -> None:
    row = _draft_row(_invoice(status="paid"))
    session = MagicMock()
    session.execute.return_value.one_or_none.return_value = row
    _patch(monkeypatch, session)

    with pytest.raises(HTTPException) as exc:
        payments.approve(row.PaymentDraft.id, [OWN])

    assert exc.value.status_code == 409
    assert row.PaymentDraft.status == "draft"
    session.commit.assert_not_called()


def test_approve_returns_the_qr_for_the_frozen_values(monkeypatch) -> None:
    row = _draft_row(_invoice())
    session = MagicMock()
    session.execute.return_value.one_or_none.return_value = row
    _patch(monkeypatch, session)

    result = payments.approve(row.PaymentDraft.id, [OWN])

    assert row.PaymentDraft.status == "approved"
    assert result["payload"].split("\n")[5:8] == ["Stadtwerke", IBAN, "EUR49.90"]
    assert result["qr"].startswith("data:image/svg+xml")
    session.commit.assert_called_once()

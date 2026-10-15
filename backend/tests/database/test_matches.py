import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.database import matches
from app.database.models.finance.invoice import Invoice
from app.database.models.finance.invoice_match import InvoiceMatch
from app.finance.matching import Proposal

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)
OWN = uuid.UUID("00000000-0000-0000-0000-000000000010")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000020")
VALID_IBAN = "DE89370400440532013000"


def _invoice(**overrides: object) -> Invoice:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "email_id": uuid.uuid4(),
        "position": 0,
        "payee": "Stadtwerke",
        "iban": VALID_IBAN,
        "amount": Decimal("10.00"),
        "currency": "EUR",
        "status": "open",
        "issues": [],
        "edited_fields": [],
    }
    values.update(overrides)
    return Invoice(**values)  # type: ignore[arg-type]


def _apply(row, proposals, existing=None):
    existing = {} if existing is None else existing
    added: list[InvoiceMatch] = []
    removed: list[InvoiceMatch] = []
    counts = matches.apply_proposals(
        row, proposals, existing, add=added.append, remove=removed.append, now=NOW
    )
    return counts, added, removed


def test_link_creates_automatic_match_and_marks_paid() -> None:
    row = _invoice()
    tx = uuid.uuid4()

    counts, [match], _ = _apply(row, [Proposal(row.id, tx, "linked", ("amount", "iban"))])

    assert counts == (1, 0)
    assert (match.status, match.source, match.signals) == ("linked", "auto", ["amount", "iban"])
    assert (row.status, row.paid_by, row.paid_at) == ("paid", "match", NOW)


def test_suggestion_leaves_the_invoice_open() -> None:
    row = _invoice()

    counts, [match], _ = _apply(
        row, [Proposal(row.id, uuid.uuid4(), "suggested", ("amount", "name"))]
    )

    assert counts == (0, 1)
    assert match.status == "suggested"
    assert row.status == "open"


def test_known_suggestion_is_not_added_twice() -> None:
    row = _invoice()
    tx = uuid.uuid4()
    known = InvoiceMatch(invoice_id=row.id, transaction_id=tx, status="suggested", source="auto")

    counts, added, _ = _apply(
        row, [Proposal(row.id, tx, "suggested", ("amount", "name"))], {(row.id, tx): known}
    )

    assert counts == (0, 0)
    assert added == []


def test_link_drops_the_invoices_other_suggestions() -> None:
    row = _invoice()
    old_tx, new_tx = uuid.uuid4(), uuid.uuid4()
    old = InvoiceMatch(invoice_id=row.id, transaction_id=old_tx, status="suggested", source="auto")
    rejected_tx = uuid.uuid4()
    rejected = InvoiceMatch(
        invoice_id=row.id, transaction_id=rejected_tx, status="rejected", source="auto"
    )
    existing = {(row.id, old_tx): old, (row.id, rejected_tx): rejected}

    _, _, removed = _apply(
        row, [Proposal(row.id, new_tx, "linked", ("amount", "iban"))], existing
    )

    assert removed == [old]
    assert (row.id, rejected_tx) in existing


def _owned_session(match: InvoiceMatch, invoice: Invoice, mailbox: uuid.UUID) -> MagicMock:
    session = MagicMock()
    owned = MagicMock()
    owned.one_or_none.return_value = SimpleNamespace(
        InvoiceMatch=match, Invoice=invoice, mailbox_id=mailbox
    )
    free = MagicMock()
    free.first.return_value = None
    session.execute.side_effect = [owned, free, MagicMock()]
    return session


def _patch(monkeypatch: pytest.MonkeyPatch, session: MagicMock) -> None:
    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(matches, "get_session", fake_get_session)


def test_undoing_an_automatic_link_reopens_the_invoice(monkeypatch) -> None:
    invoice = _invoice(status="paid", paid_by="match", paid_at=NOW)
    match = InvoiceMatch(
        id=uuid.uuid4(), invoice_id=invoice.id, transaction_id=uuid.uuid4(),
        status="linked", source="auto",
    )
    session = _owned_session(match, invoice, OWN)
    _patch(monkeypatch, session)

    matches.reject(match.id, [OWN])

    assert match.status == "rejected"
    assert (invoice.status, invoice.paid_by, invoice.paid_at) == ("open", None, None)
    session.commit.assert_called_once()


def test_rejecting_a_suggestion_keeps_the_invoice_open(monkeypatch) -> None:
    invoice = _invoice()
    match = InvoiceMatch(
        id=uuid.uuid4(), invoice_id=invoice.id, transaction_id=uuid.uuid4(),
        status="suggested", source="auto",
    )
    _patch(monkeypatch, _owned_session(match, invoice, OWN))

    matches.reject(match.id, [OWN])

    assert match.status == "rejected"
    assert invoice.status == "open"


def test_confirming_a_suggestion_links_it_as_the_owner(monkeypatch) -> None:
    invoice = _invoice()
    match = InvoiceMatch(
        id=uuid.uuid4(), invoice_id=invoice.id, transaction_id=uuid.uuid4(),
        status="suggested", source="auto",
    )
    session = _owned_session(match, invoice, OWN)
    _patch(monkeypatch, session)

    matches.confirm(match.id, [OWN])

    assert (match.status, match.source) == ("linked", "owner")
    assert (invoice.status, invoice.paid_by) == ("paid", "match")
    session.commit.assert_called_once()


def test_someone_elses_match_is_forbidden(monkeypatch) -> None:
    invoice = _invoice()
    match = InvoiceMatch(
        id=uuid.uuid4(), invoice_id=invoice.id, transaction_id=uuid.uuid4(),
        status="suggested", source="auto",
    )
    session = _owned_session(match, invoice, OTHER)
    _patch(monkeypatch, session)

    with pytest.raises(HTTPException) as exc:
        matches.reject(match.id, [OWN])

    assert exc.value.status_code == 403
    session.commit.assert_not_called()

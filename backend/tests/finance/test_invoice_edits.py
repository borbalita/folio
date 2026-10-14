from datetime import UTC, date, datetime
from decimal import Decimal

from app.database.models.finance.invoice import Invoice
from app.finance.invoice_edits import apply_edit, set_paid

VALID_IBAN = "DE89370400440532013000"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


def _needs_info() -> Invoice:
    return Invoice(
        position=0,
        payee="Stadtwerke",
        currency="EUR",
        status="needs_info",
        issues=["missing_iban", "missing_amount"],
        edited_fields=[],
    )


def _open() -> Invoice:
    return Invoice(
        position=0,
        payee="Stadtwerke",
        iban=VALID_IBAN,
        amount=Decimal("10.00"),
        currency="EUR",
        status="open",
        issues=[],
        edited_fields=[],
    )


def test_valid_iban_and_amount_make_a_needs_info_invoice_open() -> None:
    row = _needs_info()

    apply_edit(row, {"iban": "de89 3704 0044 0532 0130 00", "amount": Decimal("42.5")})

    assert row.status == "open"
    assert row.issues == []
    assert row.iban == VALID_IBAN
    assert row.amount == Decimal("42.50")
    assert sorted(row.edited_fields) == ["amount", "iban"]


def test_invalid_iban_stays_needs_info() -> None:
    row = _needs_info()

    apply_edit(row, {"iban": "DE89370400440532013001", "amount": Decimal(1)})

    assert row.status == "needs_info"
    assert row.issues == ["invalid_iban"]


def test_blank_values_clear_fields_and_other_fields_are_untouched() -> None:
    row = _open()
    row.reference = "Kd 77"

    apply_edit(
        row,
        {"reference": "  ", "bic": "cobadeffxxx", "due_date": date(2026, 11, 1)},
    )

    assert row.reference is None
    assert row.bic == "COBADEFFXXX"
    assert row.due_date == date(2026, 11, 1)
    assert row.payee == "Stadtwerke"
    assert sorted(row.edited_fields) == ["bic", "due_date", "reference"]
    assert row.status == "open"


def test_editing_a_field_twice_lists_it_once() -> None:
    row = _open()

    apply_edit(row, {"payee": "A"})
    apply_edit(row, {"payee": "B"})

    assert row.edited_fields == ["payee"]


def test_mark_paid_on_two_records_the_owner() -> None:
    rows = [_open(), _needs_info()]

    for row in rows:
        set_paid(row, paid=True, now=NOW)

    assert [row.status for row in rows] == ["paid", "paid"]
    assert [row.paid_by for row in rows] == ["owner", "owner"]
    assert [row.paid_at for row in rows] == [NOW, NOW]


def test_unmark_returns_each_to_open_or_needs_info() -> None:
    rows = [_open(), _needs_info()]
    for row in rows:
        set_paid(row, paid=True, now=NOW)

    for row in rows:
        set_paid(row, paid=False, now=NOW)

    assert [row.status for row in rows] == ["open", "needs_info"]
    assert [row.paid_by for row in rows] == [None, None]
    assert [row.paid_at for row in rows] == [None, None]


def test_editing_a_paid_invoice_keeps_it_paid() -> None:
    row = _open()
    set_paid(row, paid=True, now=NOW)

    apply_edit(row, {"iban": None})

    assert row.status == "paid"
    assert row.issues == ["missing_iban"]

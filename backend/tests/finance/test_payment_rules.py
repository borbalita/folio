import uuid
from decimal import Decimal

from app.database.models.finance.invoice import Invoice
from app.finance.payments import DraftValues, approve_refusal, draft_values, skip_reason

IBAN = "DE89370400440532013000"
OTHER_IBAN = "DE02120300000000202051"


def invoice(**overrides: object) -> Invoice:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "position": 0,
        "payee": "Stadtwerke",
        "iban": IBAN,
        "bic": None,
        "amount": Decimal("49.90"),
        "currency": "EUR",
        "invoice_number": "RE-1",
        "reference": None,
        "status": "open",
        "issues": [],
        "edited_fields": [],
    }
    values.update(overrides)
    return Invoice(**values)  # type: ignore[arg-type]


def test_reference_is_the_invoice_number_when_none_is_requested() -> None:
    assert draft_values(invoice()).reference == "RE-1"


def test_requested_reference_wins_over_the_invoice_number() -> None:
    assert draft_values(invoice(reference="Kd 4711 RE-1")).reference == "Kd 4711 RE-1"


def test_values_are_a_frozen_copy() -> None:
    row = invoice()
    values = draft_values(row)
    row.amount = Decimal("1.00")

    assert values == DraftValues(
        payee="Stadtwerke",
        iban=IBAN,
        bic=None,
        amount=Decimal("49.90"),
        currency="EUR",
        reference="RE-1",
    )


def test_only_open_invoices_get_a_draft() -> None:
    assert skip_reason(invoice()) is None
    assert skip_reason(invoice(status="paid")) == "not_open"
    assert skip_reason(invoice(status="needs_info")) == "not_open"


def test_approve_is_refused_for_an_invoice_paid_in_the_meantime() -> None:
    row = invoice()
    values = draft_values(row)
    row.status = "paid"

    assert approve_refusal(row, values) == "not_open"


def test_approve_is_refused_when_iban_or_amount_changed() -> None:
    row = invoice()
    values = draft_values(row)

    row.iban = OTHER_IBAN
    assert approve_refusal(row, values) == "iban_changed"
    row.iban = IBAN
    row.amount = Decimal("50.00")
    assert approve_refusal(row, values) == "amount_changed"


def test_approve_passes_when_nothing_changed() -> None:
    row = invoice()

    assert approve_refusal(row, draft_values(row)) is None

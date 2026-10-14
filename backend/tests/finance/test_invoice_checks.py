from decimal import Decimal

import pytest

from app.finance.invoice_checks import InvoiceFields, check, iban_valid, normalize_iban

VALID_DE = "DE89370400440532013000"


def _fields(**overrides: object) -> InvoiceFields:
    values: dict[str, object] = {
        "payee": "Stadtwerke Lindenstrom",
        "iban": VALID_DE,
        "amount": Decimal("42.50"),
        "currency": "EUR",
    }
    values.update(overrides)
    return InvoiceFields(**values)  # type: ignore[arg-type]


def test_normalize_iban_drops_spaces_and_uppercases() -> None:
    assert normalize_iban(" de89 3704 0044 0532 0130 00 ") == VALID_DE


@pytest.mark.parametrize(
    "iban",
    [VALID_DE, "GB82WEST12345698765432", "AT611904300234573201", "NL91ABNA0417164300"],
)
def test_real_ibans_are_valid(iban: str) -> None:
    assert iban_valid(iban)


@pytest.mark.parametrize(
    "iban",
    [
        "DE89370400440532013001",  # wrong checksum
        "DE8937040044053201300",  # one digit short
        "XX89370400440532013000",  # unknown country
        "DE89 3704 0044 0532 0130 00",  # not normalized
        "",
    ],
)
def test_broken_ibans_are_invalid(iban: str) -> None:
    assert not iban_valid(iban)


def test_complete_invoice_is_open() -> None:
    assert check(_fields()) == ("open", [])


def test_wrong_checksum_needs_info() -> None:
    status, issues = check(_fields(iban="DE89370400440532013001"))
    assert status == "needs_info"
    assert issues == ["invalid_iban"]


@pytest.mark.parametrize(
    ("overrides", "issue"),
    [
        ({"payee": None}, "missing_payee"),
        ({"payee": "  "}, "missing_payee"),
        ({"iban": None}, "missing_iban"),
        ({"amount": None}, "missing_amount"),
        ({"amount": Decimal(0)}, "amount_not_positive"),
        ({"amount": Decimal(-5)}, "amount_not_positive"),
        ({"currency": "USD"}, "currency_not_eur"),
        ({"currency": None}, "currency_not_eur"),
    ],
)
def test_each_failed_check_needs_info(overrides: dict, issue: str) -> None:
    status, issues = check(_fields(**overrides))
    assert status == "needs_info"
    assert issues == [issue]

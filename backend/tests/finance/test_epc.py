from decimal import Decimal

import pytest

from app.finance.epc import epc_payload, qr_svg_data_uri

IBAN = "DE89370400440532013000"


def test_payload_lines_follow_epc069_12() -> None:
    payload = epc_payload(
        name="Stadtwerke Berlin GmbH",
        iban=IBAN,
        bic="COBADEFFXXX",
        amount=Decimal("49.90"),
        remittance="RE-2026-0815",
    )

    assert payload.split("\n") == [
        "BCD",
        "002",
        "1",
        "SCT",
        "COBADEFFXXX",
        "Stadtwerke Berlin GmbH",
        IBAN,
        "EUR49.90",
        "",
        "",
        "RE-2026-0815",
    ]


def test_amount_has_two_decimals_and_no_separators() -> None:
    payload = epc_payload(name="A", iban=IBAN, bic=None, amount=Decimal(1234), remittance="x")

    assert payload.split("\n")[7] == "EUR1234.00"


def test_bic_is_optional() -> None:
    payload = epc_payload(name="A", iban=IBAN, bic=None, amount=Decimal(1), remittance="x")

    assert payload.split("\n")[4] == ""


def test_name_and_remittance_are_cut_to_their_limits() -> None:
    payload = epc_payload(
        name="N" * 80, iban=IBAN, bic=None, amount=Decimal(1), remittance="R" * 200
    )
    lines = payload.split("\n")

    assert lines[5] == "N" * 70
    assert lines[10] == "R" * 140


def test_without_remittance_trailing_empty_lines_are_left_out() -> None:
    payload = epc_payload(name="A", iban=IBAN, bic=None, amount=Decimal(1), remittance=None)

    assert payload.split("\n")[-1] == "EUR1.00"


def test_iban_is_written_without_spaces_in_capitals() -> None:
    payload = epc_payload(
        name="A", iban="de89 3704 0044 0532 0130 00", bic=None, amount=Decimal(1), remittance="x"
    )

    assert payload.split("\n")[6] == IBAN


@pytest.mark.parametrize("amount", ["0", "0.001", "1000000000"])
def test_amount_outside_the_epc_range_is_refused(amount: str) -> None:
    with pytest.raises(ValueError):
        epc_payload(name="A", iban=IBAN, bic=None, amount=Decimal(amount), remittance="x")


def test_qr_is_an_svg_data_uri_holding_the_payload() -> None:
    import segno

    payload = epc_payload(name="A", iban=IBAN, bic=None, amount=Decimal(1), remittance="x")
    uri = qr_svg_data_uri(payload)

    assert uri.startswith("data:image/svg+xml")
    # Same symbol as encoding the payload directly at error level M.
    assert segno.make(payload, error="m", encoding="utf-8", micro=False).designator.endswith("-M")

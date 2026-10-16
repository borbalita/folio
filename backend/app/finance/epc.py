"""EPC QR code payload ("GiroCode") for a SEPA credit transfer, per EPC069-12 version 002."""

from __future__ import annotations

from decimal import Decimal

import segno

MAX_NAME = 70
MAX_REMITTANCE = 140
MIN_AMOUNT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999.99")


def epc_payload(
    *,
    name: str,
    iban: str,
    bic: str | None,
    amount: Decimal,
    remittance: str | None,
) -> str:
    """Lines in the order the standard fixes; banking apps read them by position."""
    cents = amount.quantize(Decimal("0.01"))
    if cents != amount or not MIN_AMOUNT <= cents <= MAX_AMOUNT:
        raise ValueError(f"EPC amounts run from 0.01 to 999999999.99 EUR, got {amount}")
    lines = [
        "BCD",
        "002",
        "1",  # UTF-8
        "SCT",
        (bic or "").strip().upper(),
        name.strip()[:MAX_NAME],
        "".join(iban.split()).upper(),
        f"EUR{cents}",
        "",  # purpose code
        "",  # structured creditor reference
        (remittance or "").strip()[:MAX_REMITTANCE],
    ]
    # The standard lets trailing empty fields be left out.
    while lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def qr_svg_data_uri(payload: str) -> str:
    """The payload as a QR code image; error level M, as EPC069-12 requires."""
    return segno.make(payload, error="m", encoding="utf-8", micro=False).svg_data_uri(
        scale=4, border=4
    )

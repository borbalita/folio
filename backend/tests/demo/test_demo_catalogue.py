from decimal import Decimal

from app.demo.catalogue import VENDORS, demo_iban
from app.finance.invoice_checks import iban_valid


def test_every_vendor_sends_from_an_example_domain() -> None:
    assert len(VENDORS) == 6
    assert len({vendor.key for vendor in VENDORS}) == 6
    assert all(vendor.sender.endswith(".example") for vendor in VENDORS)
    assert all(vendor.customer_portal.endswith(".example") for vendor in VENDORS)


def test_demo_ibans_pass_the_checksum_and_cannot_be_paid() -> None:
    for vendor in VENDORS:
        iban = demo_iban(vendor.bank_code, vendor.account)

        assert iban_valid(iban)
        assert iban.startswith("DE")
        assert len(iban) == 22
        # No German bank code starts with 0, so no bank accepts a transfer to it.
        assert iban[4] == "0"
    assert len({vendor.bank_code for vendor in VENDORS}) == len(VENDORS)


def test_demo_iban_check_digits() -> None:
    assert demo_iban("37040044", "0532013000") == "DE89370400440532013000"


def test_item_price_ranges_are_positive_and_ordered() -> None:
    for vendor in VENDORS:
        assert 2 <= len(vendor.items) <= 5
        assert 1 <= vendor.max_items <= len(vendor.items)
        for item in vendor.items:
            low, high = item.price_range
            assert Decimal(0) < low <= high


def test_vendors_differ_in_style() -> None:
    assert len({vendor.layout for vendor in VENDORS}) == 3
    assert len({vendor.tone for vendor in VENDORS}) == 3
    assert len({vendor.number_format for vendor in VENDORS}) >= 5
    assert len({vendor.vat_rate for vendor in VENDORS}) >= 2
    assert all("Rechnung" in vendor.filename for vendor in VENDORS)

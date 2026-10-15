import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.finance.matching import Debit, InvoiceFacts, propose

IBAN = "DE89370400440532013000"
START = date(2026, 9, 1)


def invoice(**overrides: object) -> InvoiceFacts:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "amount": Decimal("49.90"),
        "currency": "EUR",
        "iban": IBAN,
        "invoice_number": "RE-2026-0815",
        "reference": None,
        "payee": "Stadtwerke Berlin GmbH",
        "start": START,
    }
    values.update(overrides)
    return InvoiceFacts(**values)  # type: ignore[arg-type]


def debit(**overrides: object) -> Debit:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "booking_date": START + timedelta(days=10),
        "amount": Decimal("49.90"),
        "currency": "EUR",
        "counterparty_iban": None,
        "counterparty_name": None,
        "remittance": "",
    }
    values.update(overrides)
    return Debit(**values)  # type: ignore[arg-type]


def test_amount_and_iban_link_automatically() -> None:
    inv = invoice()
    paid = debit(counterparty_iban="DE89 3704 0044 0532 0130 00")

    [proposal] = propose(inv, [paid], rejected=set(), taken=set())

    assert proposal.transaction_id == paid.id
    assert proposal.status == "linked"
    assert proposal.signals == ("amount", "iban")


def test_amount_and_invoice_number_in_text_link() -> None:
    inv = invoice(iban=None)
    paid = debit(remittance="Rechnung re2026 0815 Kd 4711")

    [proposal] = propose(inv, [paid], rejected=set(), taken=set())

    assert proposal.status == "linked"
    assert proposal.signals == ("amount", "reference")


def test_amount_and_similar_name_only_is_a_suggestion() -> None:
    inv = invoice()
    maybe = debit(counterparty_name="STADTWERKE BERLIN")

    [proposal] = propose(inv, [maybe], rejected=set(), taken=set())

    assert proposal.status == "suggested"
    assert proposal.signals == ("amount", "name")


def test_two_strong_candidates_are_both_suggestions() -> None:
    inv = invoice()
    first = debit(counterparty_iban=IBAN)
    second = debit(counterparty_iban=IBAN, booking_date=START + timedelta(days=40))

    proposals = propose(inv, [first, second], rejected=set(), taken=set())

    assert {p.transaction_id for p in proposals} == {first.id, second.id}
    assert {p.status for p in proposals} == {"suggested"}


def test_rejected_pair_is_not_proposed_again() -> None:
    inv = invoice()
    maybe = debit(counterparty_name="Stadtwerke")

    assert propose(inv, [maybe], rejected={maybe.id}, taken=set()) == []


def test_debit_linked_to_another_invoice_is_skipped() -> None:
    inv = invoice()
    paid = debit(counterparty_iban=IBAN)

    assert propose(inv, [paid], rejected=set(), taken={paid.id}) == []


def test_window_is_start_to_120_days_later() -> None:
    inv = invoice()
    before = debit(counterparty_iban=IBAN, booking_date=START - timedelta(days=1))
    first_day = debit(counterparty_iban=IBAN, booking_date=START)
    last_day = debit(counterparty_iban=IBAN, booking_date=START + timedelta(days=120))
    after = debit(counterparty_iban=IBAN, booking_date=START + timedelta(days=121))

    proposals = propose(inv, [before, first_day, last_day, after], rejected=set(), taken=set())

    assert {p.transaction_id for p in proposals} == {first_day.id, last_day.id}


def test_different_amount_never_matches() -> None:
    inv = invoice()
    other = debit(amount=Decimal("49.00"), counterparty_iban=IBAN, counterparty_name="Stadtwerke")

    assert propose(inv, [other], rejected=set(), taken=set()) == []


def test_short_reference_is_ignored() -> None:
    inv = invoice(iban=None, invoice_number="12", reference=None)
    other = debit(remittance="Kundennr 12 Abschlag")

    assert propose(inv, [other], rejected=set(), taken=set()) == []


def test_legal_form_alone_is_not_a_shared_name() -> None:
    inv = invoice(payee="Muster GmbH")
    other = debit(counterparty_name="Andere GmbH")

    assert propose(inv, [other], rejected=set(), taken=set()) == []


def test_strong_beats_weak_candidates() -> None:
    inv = invoice()
    strong = debit(counterparty_iban=IBAN)
    weak = debit(counterparty_name="Stadtwerke", booking_date=START + timedelta(days=3))

    [proposal] = propose(inv, [strong, weak], rejected=set(), taken=set())

    assert proposal.transaction_id == strong.id
    assert proposal.status == "linked"

import uuid
from datetime import date, timedelta
from itertools import pairwise

import pytest

from app.database.models.finance.invoice import InvoiceStatus
from app.database.models.finance.invoice_match import MatchStatus
from app.demo.accounts import DemoAccounts
from app.demo.base_state import build_base_state
from app.finance.invoice_edits import PAID_BY_INVOICE, PAID_BY_MATCH
from app.finance.matching import Debit, InvoiceFacts, propose

TODAY = date(2026, 10, 21)
ACCOUNTS = DemoAccounts(mailbox_id=uuid.uuid4(), account_id=uuid.uuid4())
TO = "demo+1@folio.example"
REAL_BRANDS = ("REWE", "EDEKA", "Telekom", "Vodafone", "Stadtwerke", "Spreewerk")


def _build(today: date = TODAY):
    return build_base_state(today, ACCOUNTS, to_address=TO)


def _matched_ids(rows, status: str) -> set[uuid.UUID]:
    return {match.invoice_id for match in rows.matches if match.status == status}


def test_base_state_counts_match_the_spec_table() -> None:
    rows = _build()
    suggested = _matched_ids(rows, MatchStatus.SUGGESTED)
    open_rows = [
        i
        for i in rows.invoices
        if i.status == InvoiceStatus.OPEN and i.id not in suggested
    ]

    assert len(rows.invoices) == 9
    assert (
        sum(1 for i in open_rows if TODAY <= i.due_date <= TODAY + timedelta(days=7))
        == 2
    )
    assert sum(1 for i in open_rows if i.due_date < TODAY) == 1
    assert sum(1 for i in rows.invoices if i.paid_by == PAID_BY_MATCH) == 3
    assert _matched_ids(rows, MatchStatus.LINKED) == {
        i.id for i in rows.invoices if i.paid_by == PAID_BY_MATCH
    }
    assert len(suggested) == 1
    assert all(
        i.status == InvoiceStatus.OPEN for i in rows.invoices if i.id in suggested
    )
    assert sum(1 for i in rows.invoices if i.paid_by == PAID_BY_INVOICE) == 1
    online = [i for i in rows.invoices if i.status == InvoiceStatus.NEEDS_INFO]
    assert len(online) == 1
    assert online[0].issues == ["invoice_online"]
    assert online[0].attachment_id is None


@pytest.mark.parametrize(
    "today",
    [date(2026, 10, 21), date(2026, 1, 31), date(2026, 3, 1), date(2028, 2, 29)],
)
def test_dates_follow_today(today: date) -> None:
    rows = _build(today)

    for invoice in rows.invoices:
        if invoice.invoice_date is not None:
            assert invoice.invoice_date <= today
            assert invoice.due_date >= invoice.invoice_date
    for tx in rows.transactions:
        assert today - timedelta(days=90) <= tx.booking_date <= today
    for email in rows.emails:
        assert email.sent_at.date() <= today
    due_dates = sorted(
        i.due_date for i in rows.invoices if i.status == InvoiceStatus.OPEN
    )
    assert today + timedelta(days=4) in due_dates


def test_base_state_is_realistic() -> None:
    rows = _build()
    names = [tx.counterparty_name or "" for tx in rows.transactions] + [
        i.payee or "" for i in rows.invoices
    ]

    assert 34 <= len(rows.transactions) <= 40
    assert sum(1 for tx in rows.transactions if tx.amount > 0) >= 3
    assert not any(
        brand.lower() in name.lower() for brand in REAL_BRANDS for name in names
    )
    by_id = {tx.id: tx for tx in rows.transactions}
    invoices = {i.id: i for i in rows.invoices}
    for match in rows.matches:
        if match.status == MatchStatus.LINKED:
            tx, invoice = by_id[match.transaction_id], invoices[match.invoice_id]
            assert tx.amount == -invoice.amount
            assert tx.remittance == invoice.reference
            assert invoice.paid_at.date() == tx.booking_date


def test_rows_reference_each_other() -> None:
    rows = _build()
    emails = {e.id for e in rows.emails}
    attachments = {a.id for a in rows.attachments}
    invoices = {i.id for i in rows.invoices}
    transactions = {t.id for t in rows.transactions}

    assert all(i.email_id in emails for i in rows.invoices)
    for invoice in rows.invoices:
        if invoice.status == InvoiceStatus.NEEDS_INFO:
            assert invoice.attachment_id is None
        else:
            assert invoice.attachment_id in attachments
    assert all(a.email_id in emails for a in rows.attachments)
    assert all(
        m.invoice_id in invoices and m.transaction_id in transactions
        for m in rows.matches
    )
    assert all(e.mailbox_id == ACCOUNTS.mailbox_id for e in rows.emails)
    assert all(t.account_id == ACCOUNTS.account_id for t in rows.transactions)
    assert rows.all()[: len(rows.emails)] == rows.emails


def test_matching_adds_nothing_to_the_base_state() -> None:
    rows = _build()
    sent = {e.id: e.sent_at for e in rows.emails}
    debits = [
        Debit(
            id=tx.id,
            booking_date=tx.booking_date,
            amount=-tx.amount,
            currency=tx.currency,
            counterparty_iban=tx.counterparty_iban,
            counterparty_name=tx.counterparty_name,
            remittance=tx.remittance,
        )
        for tx in rows.transactions
        if tx.amount < 0
    ]
    taken = {m.transaction_id for m in rows.matches if m.status == MatchStatus.LINKED}
    proposals = []
    for invoice in rows.invoices:
        if invoice.status != InvoiceStatus.OPEN:
            continue
        facts = InvoiceFacts(
            id=invoice.id,
            amount=invoice.amount,
            currency=invoice.currency,
            iban=invoice.iban,
            invoice_number=invoice.invoice_number,
            reference=invoice.reference,
            payee=invoice.payee,
            start=invoice.invoice_date or sent[invoice.email_id].date(),
        )
        proposals += propose(facts, debits, rejected=set(), taken=taken)

    seeded = {
        (m.invoice_id, m.transaction_id)
        for m in rows.matches
        if m.status == MatchStatus.SUGGESTED
    }
    assert {(p.invoice_id, p.transaction_id) for p in proposals} == seeded
    assert all(p.status == "suggested" for p in proposals)


def test_two_builds_do_not_collide() -> None:
    first, second = _build(), _build()

    assert not {e.message_id for e in first.emails} & {
        e.message_id for e in second.emails
    }
    assert not {t.dedup_key for t in first.transactions} & {
        t.dedup_key for t in second.transactions
    }


def test_the_ui_overdue_count_matches_the_spec() -> None:
    rows = _build()
    unpaid = [i for i in rows.invoices if i.status == InvoiceStatus.OPEN]

    # The invoice list marks every unpaid invoice past its due date as overdue.
    assert sum(1 for i in unpaid if i.due_date < TODAY) == 1


def test_invoice_numbers_carry_the_invoice_year() -> None:
    rows = _build(date(2027, 1, 5))

    for invoice in rows.invoices:
        if invoice.invoice_number and invoice.invoice_date.year == 2026:
            assert "2027" not in invoice.invoice_number


def test_no_vendor_bills_twice_within_two_weeks() -> None:
    rows = _build()
    by_payee: dict[str, list[date]] = {}
    for email in rows.emails:
        by_payee.setdefault(email.from_name, []).append(email.sent_at.date())

    for days in by_payee.values():
        days.sort()
        assert all((b - a).days >= 14 for a, b in pairwise(days)), days

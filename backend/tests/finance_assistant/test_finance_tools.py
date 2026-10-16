from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.database import bank_connections, invoices, payments, transactions
from app.finance_assistant import agent, tools
from app.finance_assistant.deps import FinanceAgentDeps

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MAILBOX = uuid.uuid4()
OPEN_ID = str(uuid.uuid4())
PAID_ID = str(uuid.uuid4())


def deps() -> FinanceAgentDeps:
    return FinanceAgentDeps(user_id=USER_ID, thread_id=uuid.uuid4(), mailbox_ids=[MAILBOX])


def invoice(id_: str, status: str, payee: str) -> dict:
    return {
        "id": id_,
        "payee": payee,
        "amount": "120.00",
        "currency": "EUR",
        "dueDate": "2026-10-20",
        "status": status,
        "reference": "RE-1",
        "invoiceNumber": "1",
        "iban": "DE89370400440532013000",
    }


@pytest.fixture
def two_invoices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        invoices,
        "list_invoices",
        lambda mailbox_ids: [invoice(OPEN_ID, "open", "Stadtwerke"), invoice(PAID_ID, "paid", "Telekom")],
    )


def test_list_invoices_filters_open_and_records_ids(two_invoices: None) -> None:
    d = deps()

    text = tools.execute_list_invoices(d, status="open")

    assert OPEN_ID in text and "Stadtwerke" in text and "120.00 EUR" in text
    assert PAID_ID not in text
    assert d.seen_invoice_ids == {uuid.UUID(OPEN_ID)}


def test_list_invoices_with_none_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(invoices, "list_invoices", lambda mailbox_ids: [])

    assert tools.execute_list_invoices(deps(), status="open") == "No invoices found."


def test_get_invoice_records_its_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        invoices, "get_invoice_item", lambda invoice_id, mailbox_ids: invoice(OPEN_ID, "open", "Stadtwerke")
    )
    d = deps()

    text = tools.execute_get_invoice(d, uuid.UUID(OPEN_ID))

    assert "DE89370400440532013000" in text
    assert d.seen_invoice_ids == {uuid.UUID(OPEN_ID)}


def test_prepare_payments_records_drafts_and_reports_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft_id = str(uuid.uuid4())
    calls: list[list[uuid.UUID]] = []

    def create_drafts(invoice_ids, mailbox_ids):
        calls.append(invoice_ids)
        return {
            "drafts": [
                {"id": draft_id, "invoiceId": OPEN_ID, "payee": "Stadtwerke", "amount": "120.00", "currency": "EUR"}
            ],
            "skipped": [{"invoiceId": PAID_ID, "reason": "not_open"}],
        }

    monkeypatch.setattr(payments, "create_drafts", create_drafts)
    d = deps()

    text = tools.execute_prepare_payments(d, [uuid.UUID(OPEN_ID), uuid.UUID(PAID_ID)])

    assert calls == [[uuid.UUID(OPEN_ID), uuid.UUID(PAID_ID)]]
    assert draft_id in text and "await" in text.lower()
    assert f"Skipped invoice {PAID_ID}: not open" in text
    assert d.seen_draft_ids == {uuid.UUID(draft_id)}


def test_search_transactions_scoped_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def search(user_id, *, text, since, until, limit):
        seen.update(user_id=user_id, text=text, since=since, limit=limit)
        return [
            {"date": "2026-10-01", "bank": "N26", "counterparty": "REWE", "amount": "-12.30",
             "currency": "EUR", "remittance": "Einkauf"}
        ]

    monkeypatch.setattr(transactions, "search_transactions", search)

    text = tools.execute_search_transactions(deps(), "rewe", date(2026, 9, 1), None, 20)

    assert seen == {"user_id": USER_ID, "text": "rewe", "since": date(2026, 9, 1), "limit": 20}
    assert "REWE" in text and "-12.30 EUR" in text


def test_list_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bank_connections,
        "list_connections",
        lambda user_id: [
            {"bank": "N26", "connected": True, "status": "active", "validUntil": "2027-04-07T00:00:00+00:00", "accounts": []},
            {"bank": "ING", "connected": False, "status": None, "validUntil": None, "accounts": []},
        ],
    )

    text = tools.execute_list_accounts(deps())

    assert "N26: connected, active, valid until 2027-04-07" in text
    assert "ING: not connected" in text


def test_no_tool_can_approve() -> None:
    names = set(agent.get_agent()._function_toolset.tools)

    assert names == {
        "list_invoices",
        "get_invoice",
        "search_transactions",
        "list_accounts",
        "prepare_payments",
    }


def test_unknown_invoice_is_told_to_the_model_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(invoice_id, mailbox_ids):
        raise HTTPException(404, "Invoice not found")

    monkeypatch.setattr(invoices, "get_invoice_item", missing)
    d = deps()
    unknown = uuid.uuid4()

    text = tools.execute_get_invoice(d, unknown)

    assert text == f"Invoice {unknown} was not found. List the invoices to get valid ids."
    assert d.seen_invoice_ids == set()


def test_prepare_payments_with_a_bad_id_is_told_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(invoice_ids, mailbox_ids):
        raise HTTPException(404, "Invoice not found")

    monkeypatch.setattr(payments, "create_drafts", refuse)
    d = deps()

    text = tools.execute_prepare_payments(d, [uuid.uuid4()])

    assert "No payments were prepared" in text
    assert "await" not in text.lower()
    assert d.seen_draft_ids == set()


def test_all_skipped_says_nothing_awaits_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        payments,
        "create_drafts",
        lambda invoice_ids, mailbox_ids: {"drafts": [], "skipped": [{"invoiceId": PAID_ID, "reason": "not_open"}]},
    )

    text = tools.execute_prepare_payments(deps(), [uuid.UUID(PAID_ID)])

    assert "No payments were prepared." in text
    assert "await" not in text.lower()


def test_already_approved_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        payments,
        "create_drafts",
        lambda invoice_ids, mailbox_ids: {
            "drafts": [],
            "skipped": [{"invoiceId": OPEN_ID, "reason": "already_approved"}],
        },
    )

    text = tools.execute_prepare_payments(deps(), [uuid.UUID(OPEN_ID)])

    assert f"Skipped invoice {OPEN_ID}: a payment is already approved" in text
    assert "No payments were prepared." in text

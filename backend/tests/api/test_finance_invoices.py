from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.database import invoices, mailboxes, matches
from tests.conftest import TEST_USER_ID

OWN_MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000010")
OTHER_MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000020")
EMAIL_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")
ATTACHMENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000040")
INVOICE_ID = uuid.UUID("00000000-0000-0000-0000-000000000050")


@pytest.fixture(autouse=True)
def finance_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)


def _owns_mailbox(user_id: uuid.UUID) -> list[uuid.UUID]:
    return [OWN_MAILBOX]


def test_invoice_routes_are_forbidden_for_another_user(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)

    assert authed_client.get("/finance/invoices").status_code == 403
    assert authed_client.get(f"/finance/invoices/{EMAIL_ID}").status_code == 403
    assert authed_client.get(f"/finance/attachments/{ATTACHMENT_ID}").status_code == 403
    assert (
        authed_client.patch(
            f"/finance/invoices/items/{INVOICE_ID}", json={"payee": "X"}
        ).status_code
        == 403
    )
    assert (
        authed_client.post(
            "/finance/invoices/items/paid",
            json={"ids": [str(INVOICE_ID)], "paid": True},
        ).status_code
        == 403
    )


def test_invoice_routes_are_forbidden_without_a_mailbox(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [])

    assert authed_client.get("/finance/invoices").status_code == 403
    assert authed_client.get(f"/finance/invoices/{EMAIL_ID}").status_code == 403
    assert authed_client.get(f"/finance/attachments/{ATTACHMENT_ID}").status_code == 403


def test_owner_lists_invoices_scoped_to_their_mailboxes(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[uuid.UUID]] = []
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)

    def list_invoices(mailbox_ids: list[uuid.UUID]) -> list[dict[str, str]]:
        seen.append(mailbox_ids)
        return [{"id": str(EMAIL_ID), "subject": "Invoice 42"}]

    monkeypatch.setattr(invoices, "list_invoices", list_invoices)

    response = authed_client.get("/finance/invoices")

    assert response.status_code == 200
    assert response.json()[0]["subject"] == "Invoice 42"
    assert seen == [[OWN_MAILBOX]]


def test_owner_gets_an_invoice_scoped_to_their_mailboxes(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    seen: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    def get_invoice(
        email_id: uuid.UUID, mailbox_ids: list[uuid.UUID]
    ) -> dict[str, str]:
        seen.append((email_id, mailbox_ids))
        return {"id": str(email_id), "subject": "Invoice 42"}

    monkeypatch.setattr(invoices, "get_invoice", get_invoice)

    response = authed_client.get(f"/finance/invoices/{EMAIL_ID}")

    assert response.status_code == 200
    assert response.json()["subject"] == "Invoice 42"
    assert seen == [(EMAIL_ID, [OWN_MAILBOX])]


def test_owner_downloads_a_stored_pdf_inline(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    monkeypatch.setattr(
        invoices,
        "get_attachment_file",
        lambda attachment_id, mailbox_ids: invoices.AttachmentFile(
            filename="März invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 fake",
        ),
    )

    response = authed_client.get(f"/finance/attachments/{ATTACHMENT_ID}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert "M%C3%A4rz%20invoice.pdf" in response.headers["content-disposition"]
    assert response.content == b"%PDF-1.4 fake"


def _fake_session(row: SimpleNamespace | None):
    result = SimpleNamespace(one_or_none=lambda: row)
    session = SimpleNamespace(execute=lambda _statement: result)

    @contextmanager
    def factory():
        yield session

    return factory


def _attachment_row(mailbox_id: uuid.UUID, content: bytes | None) -> SimpleNamespace:
    return SimpleNamespace(
        filename="invoice.pdf",
        content_type="application/pdf",
        content=content,
        mailbox_id=mailbox_id,
    )


def test_attachment_in_another_mailbox_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _attachment_row(OTHER_MAILBOX, b"%PDF")
    monkeypatch.setattr(invoices, "get_session", _fake_session(row))

    with pytest.raises(HTTPException) as caught:
        invoices.get_attachment_file(ATTACHMENT_ID, [OWN_MAILBOX])

    assert caught.value.status_code == 403


def test_skipped_attachment_has_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _attachment_row(OWN_MAILBOX, None)
    monkeypatch.setattr(invoices, "get_session", _fake_session(row))

    with pytest.raises(HTTPException) as caught:
        invoices.get_attachment_file(ATTACHMENT_ID, [OWN_MAILBOX])

    assert caught.value.status_code == 404


def test_missing_attachment_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(invoices, "get_session", _fake_session(None))

    with pytest.raises(HTTPException) as caught:
        invoices.get_attachment_file(ATTACHMENT_ID, [OWN_MAILBOX])

    assert caught.value.status_code == 404


def test_own_stored_attachment_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _attachment_row(OWN_MAILBOX, b"%PDF")
    monkeypatch.setattr(invoices, "get_session", _fake_session(row))

    file = invoices.get_attachment_file(ATTACHMENT_ID, [OWN_MAILBOX])

    assert file.content == b"%PDF"


def test_owner_edits_only_the_fields_sent(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    seen: list[tuple[uuid.UUID, dict, list[uuid.UUID]]] = []

    def update_invoice(
        invoice_id: uuid.UUID, changes: dict, mailbox_ids: list[uuid.UUID]
    ) -> dict[str, str]:
        seen.append((invoice_id, changes, mailbox_ids))
        return {"id": str(invoice_id), "status": "open"}

    monkeypatch.setattr(invoices, "update_invoice", update_invoice)
    matched: list[uuid.UUID] = []
    monkeypatch.setattr(matches, "match_for_user", matched.append)
    monkeypatch.setattr(
        invoices,
        "get_invoice_item",
        lambda invoice_id, mailbox_ids: {"id": str(invoice_id), "status": "paid"},
    )

    response = authed_client.patch(
        f"/finance/invoices/items/{INVOICE_ID}",
        json={"amount": "42.5", "dueDate": "2026-11-01", "reference": None},
    )

    assert response.status_code == 200
    # The edit is re-matched, and the answer shows the invoice after matching.
    assert matched == [TEST_USER_ID]
    assert response.json()["status"] == "paid"
    assert seen == [
        (
            INVOICE_ID,
            {
                "amount": Decimal("42.5"),
                "due_date": date(2026, 11, 1),
                "reference": None,
            },
            [OWN_MAILBOX],
        )
    ]


def test_edit_with_a_bad_date_is_rejected(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    monkeypatch.setattr(
        invoices, "update_invoice", lambda *_args: pytest.fail("not called")
    )

    response = authed_client.patch(
        f"/finance/invoices/items/{INVOICE_ID}", json={"dueDate": "soon"}
    )

    assert response.status_code == 422


def test_owner_marks_several_invoices_paid(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    other = uuid.uuid4()
    seen: list[tuple[list[uuid.UUID], bool, list[uuid.UUID]]] = []

    def set_invoices_paid(
        ids: list[uuid.UUID], paid: bool, mailbox_ids: list[uuid.UUID]
    ) -> list[dict[str, str]]:
        seen.append((ids, paid, mailbox_ids))
        return [{"id": str(item), "status": "paid"} for item in ids]

    monkeypatch.setattr(invoices, "set_invoices_paid", set_invoices_paid)

    response = authed_client.post(
        "/finance/invoices/items/paid",
        json={"ids": [str(INVOICE_ID), str(other)], "paid": True},
    )

    assert response.status_code == 200
    assert [item["status"] for item in response.json()] == ["paid", "paid"]
    assert seen == [([INVOICE_ID, other], True, [OWN_MAILBOX])]


@pytest.mark.parametrize("action", ["confirm", "reject"])
def test_owner_confirms_or_rejects_a_match(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", _owns_mailbox)
    match_id = uuid.uuid4()
    seen: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    def decide(mid: uuid.UUID, mailbox_ids: list[uuid.UUID]) -> uuid.UUID:
        seen.append((mid, mailbox_ids))
        return INVOICE_ID

    monkeypatch.setattr(matches, action, decide)
    monkeypatch.setattr(
        invoices,
        "get_invoice_item",
        lambda invoice_id, mailbox_ids: {"id": str(invoice_id)},
    )

    response = authed_client.post(f"/finance/matches/{match_id}/{action}")

    assert response.status_code == 200
    assert response.json() == {"id": str(INVOICE_ID)}
    assert seen == [(match_id, [OWN_MAILBOX])]


def test_match_routes_are_forbidden_for_another_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    response = authed_client.post(f"/finance/matches/{uuid.uuid4()}/confirm")

    assert response.status_code == 403

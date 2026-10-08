from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import invoices, mailboxes

OWN_MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000010")
OTHER_MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000020")
EMAIL_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")
ATTACHMENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000040")


def _owns_mailbox(user_id: uuid.UUID) -> list[uuid.UUID]:
    return [OWN_MAILBOX]


def test_invoice_routes_are_forbidden_without_a_mailbox(
    authed_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [])

    assert authed_client.get("/email/invoices").status_code == 403
    assert authed_client.get(f"/email/invoices/{EMAIL_ID}").status_code == 403
    assert authed_client.get(f"/email/attachments/{ATTACHMENT_ID}").status_code == 403


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

    response = authed_client.get("/email/invoices")

    assert response.status_code == 200
    assert response.json()[0]["subject"] == "Invoice 42"
    assert seen == [[OWN_MAILBOX]]


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

    response = authed_client.get(f"/email/attachments/{ATTACHMENT_ID}")

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

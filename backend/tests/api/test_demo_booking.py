from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.demo import booking
from tests.conftest import TEST_USER_ID

PAYMENT = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


def test_demo_payment_routes_do_not_exist_without_a_demo_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", None)

    assert authed_client.get("/finance/demo/payments").status_code == 404
    assert (
        authed_client.post(f"/finance/demo/payments/{PAYMENT}/book").status_code == 404
    )


def test_the_owner_cannot_book_demo_payments(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(
        booking, "book", lambda *_args, **_kw: pytest.fail("not called")
    )

    assert authed_client.get("/finance/demo/payments").status_code == 403
    assert (
        authed_client.post(f"/finance/demo/payments/{PAYMENT}/book").status_code == 403
    )


def test_the_demo_user_lists_and_books_their_payments(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    seen: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        booking,
        "approved_payments",
        lambda user_id: [{"id": str(PAYMENT), "user": str(user_id)}],
    )

    def book(user_id: uuid.UUID, draft_id: uuid.UUID) -> dict:
        seen.append((user_id, draft_id))
        return {"booked": True, "paymentStatus": "completed", "invoiceStatus": "paid"}

    monkeypatch.setattr(booking, "book", book)

    listed = authed_client.get("/finance/demo/payments")
    booked = authed_client.post(f"/finance/demo/payments/{PAYMENT}/book")

    assert listed.status_code == 200
    assert listed.json() == [{"id": str(PAYMENT), "user": str(TEST_USER_ID)}]
    assert booked.status_code == 200
    assert booked.json()["invoiceStatus"] == "paid"
    assert seen == [(TEST_USER_ID, PAYMENT)]


def test_the_demo_user_sends_a_live_invoice(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.demo import live

    monkeypatch.setattr(settings, "demo_user_id", TEST_USER_ID)
    seen: list[tuple[uuid.UUID, str]] = []

    def send(user_id: uuid.UUID, kind: str) -> dict:
        seen.append((user_id, kind))
        return {
            "sent": {"kind": "normal"},
            "invoices": [],
            "failures": 0,
            "error": None,
        }

    monkeypatch.setattr(live, "send_invoice", send)
    ensured: list[tuple[uuid.UUID, str]] = []
    monkeypatch.setattr(
        "app.api.demo.chats.ensure_user",
        lambda user_id, email: ensured.append((user_id, email)),
    )

    sent = authed_client.post("/finance/demo/invoices", json={"kind": "random"})
    refused = authed_client.post("/finance/demo/invoices", json={"kind": "lottery"})

    assert sent.status_code == 200
    assert seen == [(TEST_USER_ID, "random")]
    # A demo user who never chatted has no users row; the demo mailbox needs one.
    assert ensured == [(TEST_USER_ID, "test@example.com")]
    assert refused.status_code == 422


def test_the_owner_cannot_send_live_invoices(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_user_id", uuid.uuid4())

    assert (
        authed_client.post(
            "/finance/demo/invoices", json={"kind": "normal"}
        ).status_code
        == 403
    )

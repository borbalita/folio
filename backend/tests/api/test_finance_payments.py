import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import mailboxes, payments
from tests.conftest import TEST_USER_ID

OWN_MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000010")


@pytest.fixture(autouse=True)
def finance_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(mailboxes, "active_mailbox_ids", lambda user_id: [OWN_MAILBOX])


def test_owner_creates_drafts_without_choosing_an_account(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoice_id = uuid.uuid4()
    seen = []

    def create_drafts(invoice_ids, mailbox_ids):
        seen.append((invoice_ids, mailbox_ids))
        return {"drafts": [], "skipped": []}

    monkeypatch.setattr(payments, "create_drafts", create_drafts)

    response = authed_client.post(
        "/finance/payment-drafts", json={"invoiceIds": [str(invoice_id)]}
    )

    assert response.status_code == 200
    assert seen == [([invoice_id], [OWN_MAILBOX])]


@pytest.mark.parametrize("action", ["approve", "cancel"])
def test_owner_approves_or_cancels_a_draft(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    draft_id = uuid.uuid4()
    monkeypatch.setattr(
        payments, action, lambda did, mailbox_ids: {"id": str(did), "mailboxes": len(mailbox_ids)}
    )

    response = authed_client.post(f"/finance/payment-drafts/{draft_id}/{action}")

    assert response.status_code == 200
    assert response.json() == {"id": str(draft_id), "mailboxes": 1}


def test_drafts_are_read_by_id(authed_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        payments, "get_drafts", lambda ids, mailbox_ids: [{"id": str(i)} for i in ids]
    )

    response = authed_client.get(f"/finance/payment-drafts?ids={first}&ids={second}")

    assert response.json() == [{"id": str(first)}, {"id": str(second)}]


def test_payment_routes_are_forbidden_for_another_user(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    response = authed_client.post(f"/finance/payment-drafts/{uuid.uuid4()}/approve")

    assert response.status_code == 403

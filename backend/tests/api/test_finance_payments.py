import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import mailboxes, matches, payments
from tests.conftest import TEST_USER_ID

OWN_MAILBOX = uuid.UUID("00000000-0000-0000-0000-000000000010")


@pytest.fixture(autouse=True)
def finance_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(mailboxes, "invoice_mailbox_ids", lambda user_id: [OWN_MAILBOX])


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


def test_owner_cancels_a_draft(authed_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    draft_id = uuid.uuid4()
    monkeypatch.setattr(
        payments, "cancel", lambda did, mailbox_ids: {"id": str(did), "mailboxes": len(mailbox_ids)}
    )

    response = authed_client.post(f"/finance/payment-drafts/{draft_id}/cancel")

    assert response.status_code == 200
    assert response.json() == {"id": str(draft_id), "mailboxes": 1}


def test_owner_approves_a_draft_as_shown(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_id = uuid.uuid4()
    seen = []
    monkeypatch.setattr(
        payments, "approve", lambda did, mailbox_ids, changes: seen.append(changes) or {}
    )
    monkeypatch.setattr(matches, "match_for_user", lambda user_id: pytest.fail("no edit"))

    response = authed_client.post(f"/finance/payment-drafts/{draft_id}/approve")

    assert response.status_code == 200
    assert seen == [{}]


def test_owner_approves_a_draft_with_corrections(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_id = uuid.uuid4()
    seen = []
    matched = []
    monkeypatch.setattr(
        payments, "approve", lambda did, mailbox_ids, changes: seen.append(changes) or {}
    )
    monkeypatch.setattr(matches, "match_for_user", matched.append)

    response = authed_client.post(
        f"/finance/payment-drafts/{draft_id}/approve",
        json={"iban": "DE02120300000000202051", "amount": "52.10"},
    )

    assert response.status_code == 200
    assert seen == [{"iban": "DE02120300000000202051", "amount": Decimal("52.10")}]
    # A corrected IBAN or amount can make or break a match.
    assert matched == [TEST_USER_ID]


def test_approve_rejects_fields_the_qr_does_not_carry(authed_client: TestClient) -> None:
    response = authed_client.post(
        f"/finance/payment-drafts/{uuid.uuid4()}/approve", json={"dueDate": "2026-11-01"}
    )

    assert response.status_code == 422


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

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import bank_connections
from app.finance import enable_banking
from app.finance.enable_banking import (
    EbSession,
    EnableBankingError,
    EnableBankingNotConfigured,
)
from tests.conftest import TEST_USER_ID

CONNECTIONS = [{"bank": "N26", "accounts": []}]
SESSION = EbSession(
    session_id="s1", valid_until=datetime(2027, 1, 1, tzinfo=UTC), accounts=[]
)


@pytest.fixture(autouse=True)
def finance_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)
    monkeypatch.setattr(
        bank_connections, "list_connections", lambda user_id: CONNECTIONS
    )


def _patch_pending(
    monkeypatch: pytest.MonkeyPatch, pending: str | None
) -> dict[str, Any]:
    calls: dict[str, Any] = {"cleared": [], "completed": [], "sessions": []}
    monkeypatch.setattr(
        bank_connections, "find_pending", lambda user_id, state: pending
    )
    monkeypatch.setattr(
        bank_connections,
        "complete_connection",
        lambda user_id, state, session: calls["completed"].append((state, session)),
    )
    monkeypatch.setattr(
        bank_connections,
        "clear_pending",
        lambda user_id, state: calls["cleared"].append(state),
    )

    async def create_session(code: str) -> EbSession:
        calls["sessions"].append(code)
        return SESSION

    monkeypatch.setattr(enable_banking, "create_session", create_session)
    return calls


def test_lists_connections(authed_client: TestClient) -> None:
    response = authed_client.get("/finance/bank-connections")

    assert response.status_code == 200
    assert response.json() == CONNECTIONS


def test_start_returns_bank_url_and_records_state(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    begun: list[tuple[str, str]] = []
    monkeypatch.setattr(
        bank_connections,
        "begin_connection",
        lambda user_id, bank, state: begun.append((bank, state)),
    )

    async def start_authorization(bank: str, state: str) -> str:
        assert state == begun[0][1]
        return "https://bank.example/x"

    monkeypatch.setattr(enable_banking, "start_authorization", start_authorization)

    response = authed_client.post("/finance/bank-connections/ING/start")

    assert response.status_code == 200
    assert response.json() == {"url": "https://bank.example/x"}
    assert begun[0][0] == "ING"
    assert len(begun[0][1]) >= 32


def test_start_unknown_bank_is_404(authed_client: TestClient) -> None:
    response = authed_client.post("/finance/bank-connections/Revolut/start")

    assert response.status_code == 404


def test_start_without_config_is_503_naming_setting(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bank_connections, "begin_connection", lambda *a: None)

    async def start_authorization(bank: str, state: str) -> str:
        raise EnableBankingNotConfigured(
            "Enable Banking is not configured: ENABLE_BANKING_APP_ID missing"
        )

    monkeypatch.setattr(enable_banking, "start_authorization", start_authorization)

    response = authed_client.post("/finance/bank-connections/N26/start")

    assert response.status_code == 503
    assert "ENABLE_BANKING" in response.json()["detail"]


def test_start_bank_error_is_502_without_provider_body(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bank_connections, "begin_connection", lambda *a: None)

    async def start_authorization(bank: str, state: str) -> str:
        raise EnableBankingError(500, "secret provider text")

    monkeypatch.setattr(enable_banking, "start_authorization", start_authorization)

    response = authed_client.post("/finance/bank-connections/N26/start")

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not reach the bank; try again."


def test_callback_with_wrong_state_is_refused(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_pending(monkeypatch, None)

    response = authed_client.post(
        "/finance/bank-connections/callback", json={"code": "c", "state": "bad"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown or expired connection attempt."
    assert calls["sessions"] == []


def test_callback_completes_connection(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_pending(monkeypatch, "N26")

    response = authed_client.post(
        "/finance/bank-connections/callback", json={"code": "c1", "state": "st"}
    )

    assert response.status_code == 200
    assert response.json() == CONNECTIONS
    assert calls["sessions"] == ["c1"]
    assert calls["completed"] == [("st", SESSION)]


def test_callback_state_lost_before_completion_is_400(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pending(monkeypatch, "N26")

    def complete(user_id: uuid.UUID, state: str, session: EbSession) -> None:
        raise bank_connections.UnknownState

    monkeypatch.setattr(bank_connections, "complete_connection", complete)

    response = authed_client.post(
        "/finance/bank-connections/callback", json={"code": "c", "state": "st"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown or expired connection attempt."


def test_callback_bank_error_clears_pending(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_pending(monkeypatch, "N26")

    async def create_session(code: str) -> EbSession:
        raise EnableBankingError(400, '{"error": "invalid_grant"}')

    monkeypatch.setattr(enable_banking, "create_session", create_session)

    response = authed_client.post(
        "/finance/bank-connections/callback", json={"code": "c", "state": "st"}
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Bank connection failed; start it again."
    assert "invalid_grant" not in response.text
    assert calls["cleared"] == ["st"]


def test_non_owner_gets_403_on_bank_connection_routes(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    assert authed_client.get("/finance/bank-connections").status_code == 403
    assert authed_client.post("/finance/bank-connections/N26/start").status_code == 403
    callback = authed_client.post(
        "/finance/bank-connections/callback", json={"code": "c", "state": "s"}
    )
    assert callback.status_code == 403

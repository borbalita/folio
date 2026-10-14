from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import job_runs, transactions
from app.finance import transaction_sync
from app.finance.transaction_sync import BankSyncFailed
from tests.conftest import TEST_USER_ID

COUNTS = {"accounts": 3, "fetched": 10, "added": 4, "skipped": 0}


@pytest.fixture(autouse=True)
def finance_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", TEST_USER_ID)


def _last_sync(monkeypatch: pytest.MonkeyPatch, ago: timedelta | None) -> None:
    started = None if ago is None else datetime.now(UTC) - ago
    monkeypatch.setattr(job_runs, "last_started", lambda job: started)


def _record_sync(monkeypatch: pytest.MonkeyPatch, result: Any = COUNTS) -> list:
    calls: list = []

    def fake(user_id, psu_headers=None):
        calls.append((user_id, psu_headers))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(transaction_sync, "run_bank_sync", fake)
    return calls


def test_sync_now_refused_within_ten_minutes(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _last_sync(monkeypatch, timedelta(minutes=9))
    calls = _record_sync(monkeypatch)

    response = authed_client.post("/finance/bank-sync")

    assert response.status_code == 429
    assert response.json()["detail"] == "Synced less than 10 minutes ago; try again later."
    assert calls == []


def test_sync_now_runs_after_ten_minutes(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _last_sync(monkeypatch, timedelta(minutes=11))
    calls = _record_sync(monkeypatch)

    response = authed_client.post(
        "/finance/bank-sync",
        headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1", "User-Agent": "Firefox"},
    )

    assert response.status_code == 200
    assert response.json() == COUNTS
    assert calls == [
        (TEST_USER_ID, {"Psu-Ip-Address": "1.2.3.4", "Psu-User-Agent": "Firefox"})
    ]


def test_sync_now_runs_when_never_synced(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _last_sync(monkeypatch, None)
    _record_sync(monkeypatch)

    assert authed_client.post("/finance/bank-sync").status_code == 200


def test_sync_now_partial_failure_is_502(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _last_sync(monkeypatch, None)
    _record_sync(monkeypatch, BankSyncFailed("ING: Enable Banking returned 401"))

    response = authed_client.post("/finance/bank-sync")

    assert response.status_code == 502
    assert response.json()["detail"] == "Some banks could not be synced; see the job log."


def test_transactions_route_is_owner_only(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "finance_owner_user_id", uuid.uuid4())

    assert authed_client.get("/finance/transactions").status_code == 403
    assert authed_client.post("/finance/bank-sync").status_code == 403


def test_transactions_route_returns_list(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [{"id": "t1", "date": "2026-10-10", "amount": "-4.20"}]
    monkeypatch.setattr(transactions, "list_transactions", lambda user_id: rows)

    response = authed_client.get("/finance/transactions")

    assert response.status_code == 200
    assert response.json() == rows

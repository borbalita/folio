from __future__ import annotations

import asyncio
import functools
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.database import bank_connections, transactions
from app.database.bank_connections import SyncAccount
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.finance import enable_banking, transaction_sync
from app.finance.enable_banking import EnableBankingError
from app.finance.transaction_sync import BankSyncFailed, sync_all

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TODAY = date(2026, 10, 14)
N26 = SyncAccount(id=uuid.uuid4(), uid="n26-uid", bank="N26")
ING = SyncAccount(id=uuid.uuid4(), uid="ing-uid", bank="ING")


def entry(ref: str | None = None, *, status: str = "BOOK", **overrides) -> dict:
    data = {
        "entry_reference": ref,
        "transaction_amount": {"currency": "EUR", "amount": "4.20"},
        "credit_debit_indicator": "DBIT",
        "status": status,
        "booking_date": "2026-10-10",
        "creditor": {"name": "Bäckerei"},
        "remittance_information": [],
    }
    data.update(overrides)
    return data


class Store:
    """In-memory stand-in for the transactions table and its unique key."""

    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str], date] = {}

    def store(self, account_id: uuid.UUID, txs) -> int:
        before = len(self.rows)
        for tx, key in zip(txs, transactions.dedup_keys(txs), strict=True):
            self.rows.setdefault((account_id, key), tx.booking_date)
        return len(self.rows) - before

    def latest_booking_dates(self, account_ids):
        latest: dict[uuid.UUID, date] = {}
        for (account_id, _), booked in self.rows.items():
            if account_id in account_ids:
                latest[account_id] = max(booked, latest.get(account_id, booked))
        return latest


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    fake = Store()
    monkeypatch.setattr(transactions, "store", fake.store)
    monkeypatch.setattr(transactions, "latest_booking_dates", fake.latest_booking_dates)
    return fake


def targets(monkeypatch: pytest.MonkeyPatch, accounts, skipped: int = 0) -> None:
    monkeypatch.setattr(
        bank_connections, "sync_targets", lambda user_id, now: (accounts, skipped)
    )


@pytest.fixture
def pages(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[list[dict]]]:
    """Per account uid, the pages the bank returns; calls are recorded in `calls`."""
    by_uid: dict[str, list[list[dict]]] = {}
    calls: list[tuple[str, date]] = []

    async def fake_fetch(uid, date_from, *, psu_headers=None, client=None):
        calls.append((uid, date_from))
        return enable_banking.parse_page(
            [e for page in by_uid.get(uid, []) for e in page]
        )

    monkeypatch.setattr(enable_banking, "fetch_transactions", fake_fetch)
    by_uid["__calls__"] = calls  # type: ignore[assignment]
    return by_uid


def run(**kwargs):
    return asyncio.run(sync_all(USER_ID, today=TODAY, **kwargs))


def test_both_pages_are_stored(monkeypatch: pytest.MonkeyPatch, store: Store) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setattr(settings, "enable_banking_app_id", "app")
    monkeypatch.setattr(settings, "enable_banking_private_key", pem)
    monkeypatch.setattr(settings, "enable_banking_redirect_url", "https://x/cb")

    def handler(request: httpx.Request) -> httpx.Response:
        if "continuation_key" in request.url.params:
            return httpx.Response(200, json={"transactions": [entry("p2")]})
        return httpx.Response(
            200, json={"transactions": [entry("p1")], "continuation_key": "next"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        enable_banking,
        "fetch_transactions",
        functools.partial(enable_banking.fetch_transactions, client=client),
    )
    targets(monkeypatch, [N26])

    counts = run()

    assert counts["added"] == 2
    assert len(store.rows) == 2


def test_pending_entries_are_not_stored(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [ING])
    pages["ing-uid"] = [[entry("b1"), entry("p1", status="PDNG", booking_date="2026-10-20")]]

    counts = run()

    assert counts == {"accounts": 1, "fetched": 1, "added": 1, "skipped": 0, "unparsed": 0}


def test_second_run_over_overlap_adds_nothing(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [N26])
    pages["n26-uid"] = [[entry("a"), entry(None), entry(None, creditor={"name": "Kiosk"})]]

    first = run()
    second = run()

    assert first["added"] == 3
    assert second["added"] == 0
    assert len(store.rows) == 3


def test_two_identical_n26_rows_are_both_stored(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [N26])
    pages["n26-uid"] = [[entry(None), entry(None)]]

    assert run()["added"] == 2


def test_debit_and_refund_sharing_entry_reference_are_both_stored(
    monkeypatch, store, pages
) -> None:
    targets(monkeypatch, [N26])
    pages["n26-uid"] = [
        [entry("R1"), entry("R1", credit_debit_indicator="CRDT", debtor={"name": "Shop"})]
    ]

    assert run()["added"] == 2


def test_date_from_is_latest_booking_minus_seven_days(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [N26])
    store.rows[(N26.id, "x")] = date(2026, 10, 12)

    run()

    assert pages["__calls__"] == [("n26-uid", date(2026, 10, 5))]


def test_date_from_defaults_to_ninety_days(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [N26])

    run()

    assert pages["__calls__"] == [("n26-uid", TODAY - timedelta(days=90))]


def test_one_failing_bank_does_not_stop_the_others(monkeypatch, store) -> None:
    async def fetch(uid, date_from, *, psu_headers=None, client=None):
        if uid == "ing-uid":
            raise EnableBankingError(401, "expired")
        return enable_banking.parse_page([entry("ok")])

    monkeypatch.setattr(enable_banking, "fetch_transactions", fetch)
    targets(monkeypatch, [ING, N26])

    with pytest.raises(BankSyncFailed, match="ING: Enable Banking returned 401"):
        run()

    assert list(store.rows) == [(N26.id, "ref:DBIT:ok")]


def test_skipped_connections_are_counted(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [], skipped=1)

    assert run() == {
        "accounts": 0, "fetched": 0, "added": 0, "skipped": 1, "unparsed": 0
    }


def test_psu_headers_reach_the_bank_call(monkeypatch, store) -> None:
    seen = []

    async def fetch(uid, date_from, *, psu_headers=None, client=None):
        seen.append(psu_headers)
        return [], 0

    monkeypatch.setattr(enable_banking, "fetch_transactions", fetch)
    targets(monkeypatch, [N26])

    run(psu_headers={"Psu-Ip-Address": "1.2.3.4"})

    assert seen == [{"Psu-Ip-Address": "1.2.3.4"}]


def test_expired_connection_is_skipped_without_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 14, 12, tzinfo=UTC)
    live = BankConnection(
        id=uuid.uuid4(), user_id=USER_ID, bank="N26", session_id="s",
        valid_until=now + timedelta(days=30),
    )
    expired = BankConnection(
        id=uuid.uuid4(), user_id=USER_ID, bank="ING", session_id="s",
        valid_until=now - timedelta(days=1),
    )
    never = BankConnection(id=uuid.uuid4(), user_id=USER_ID, bank="PayPal")
    account = BankAccount(
        id=uuid.uuid4(), connection_id=live.id, uid="n26-uid", identification_hash="h"
    )
    session = MagicMock()
    session.scalars.side_effect = [[live, expired, never], [account]]

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(bank_connections, "get_session", fake_get_session)

    accounts, skipped = bank_connections.sync_targets(USER_ID, now)

    assert accounts == [SyncAccount(id=account.id, uid="n26-uid", bank="N26")]
    assert skipped == 2


def test_run_bank_sync_records_a_job(monkeypatch, store, pages) -> None:
    targets(monkeypatch, [N26])
    jobs = []

    def fake_run_job(job, work):
        jobs.append(job)
        return work()

    monkeypatch.setattr(transaction_sync, "run_job", fake_run_job)

    counts = transaction_sync.run_bank_sync(USER_ID)

    assert jobs == ["bank_sync"]
    assert counts["accounts"] == 1


def test_an_unreadable_entry_is_counted_and_the_rest_stored(
    monkeypatch, store, pages
) -> None:
    targets(monkeypatch, [ING])
    broken = entry("bad")
    del broken["credit_debit_indicator"]
    pages["ing-uid"] = [[entry("good"), broken]]

    counts = run()

    assert counts["added"] == 1
    assert counts["unparsed"] == 1

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.database import transactions
from app.finance.enable_banking import EbTransaction


def tx(
    *,
    day: date = date(2026, 10, 1),
    amount: str = "-9.99",
    ref: str | None = None,
    direction: str = "DBIT",
    name: str | None = "REWE",
    text: str = "",
) -> EbTransaction:
    return EbTransaction(
        booking_date=day,
        amount=Decimal(amount),
        currency="EUR",
        direction=direction,
        entry_reference=ref,
        counterparty_name=name,
        counterparty_iban=None,
        remittance=text,
        bank_code=None,
        raw={},
    )


def test_identical_fallback_rows_get_distinct_keys() -> None:
    keys = transactions.dedup_keys([tx(), tx()])

    assert len(set(keys)) == 2
    assert all(k.startswith("fb:") for k in keys)


def test_fallback_keys_are_stable_across_runs() -> None:
    rows = [tx(), tx(name="Lidl"), tx()]

    first = transactions.dedup_keys(rows)
    # A page break inside the day: the same rows, fetched as two batches in one run.
    second = transactions.dedup_keys(rows[:2] + rows[2:])
    # The ordinal counts identical rows only, so other rows between them don't matter.
    reordered = transactions.dedup_keys([rows[1], rows[0], rows[2]])

    assert first == second
    assert sorted(first) == sorted(reordered)


def test_debit_and_refund_sharing_entry_reference_get_distinct_keys() -> None:
    debit = tx(ref="R1", direction="DBIT", amount="-20.00")
    refund = tx(ref="R1", direction="CRDT", amount="20.00")

    keys = transactions.dedup_keys([debit, refund])

    assert keys == ["ref:DBIT:R1", "ref:CRDT:R1"]


def test_entry_reference_key_ignores_text_changes() -> None:
    assert transactions.dedup_keys([tx(ref="R1", text="a")]) == transactions.dedup_keys(
        [tx(ref="R1", text="b")]
    )


def test_store_compiles_on_conflict_do_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [uuid.uuid4()]

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(transactions, "get_session", fake_get_session)

    added = transactions.store(uuid.uuid4(), [tx()])

    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (account_id, dedup_key) DO NOTHING" in sql
    assert added == 1
    session.commit.assert_called_once()


def test_store_with_nothing_does_not_touch_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transactions, "get_session", None)

    assert transactions.store(uuid.uuid4(), []) == 0

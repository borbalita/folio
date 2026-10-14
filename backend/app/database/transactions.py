"""Bank transactions, stored once each however often a sync re-reads them."""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.database.engine import get_session
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.database.models.finance.transaction import Transaction
from app.finance.enable_banking import EbTransaction


def dedup_keys(txs: list[EbTransaction]) -> list[str]:
    """One key per entry, stable across syncs that re-read the same days.

    Banks fill `entry_reference` unevenly and reuse it for a debit and its refund,
    so direction is part of that key. Without one, identical rows on a day (seen
    on N26) are told apart by their ordinal among identical rows.
    """
    seen: Counter[tuple[str, ...]] = Counter()
    keys: list[str] = []
    for tx in txs:
        if tx.entry_reference:
            keys.append(f"ref:{tx.direction}:{tx.entry_reference}")
            continue
        fields = (
            tx.booking_date.isoformat(),
            str(tx.amount),
            tx.counterparty_name or "",
            tx.counterparty_iban or "",
            tx.remittance,
        )
        ordinal = seen[fields]
        seen[fields] += 1
        digest = hashlib.sha256("|".join((*fields, str(ordinal))).encode()).hexdigest()
        keys.append(f"fb:{digest}")
    return keys


def store(account_id: uuid.UUID, txs: list[EbTransaction]) -> int:
    """Insert what is new; returns how many rows were added."""
    if not txs:
        return 0
    rows = [
        {
            "account_id": account_id,
            "booking_date": tx.booking_date,
            "amount": tx.amount,
            "currency": tx.currency,
            "counterparty_name": tx.counterparty_name,
            "counterparty_iban": tx.counterparty_iban,
            "remittance": tx.remittance,
            "bank_code": tx.bank_code,
            "entry_reference": tx.entry_reference,
            "dedup_key": key,
            "raw": tx.raw,
        }
        for tx, key in zip(txs, dedup_keys(txs), strict=True)
    ]
    stmt = (
        insert(Transaction)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["account_id", "dedup_key"])
        .returning(Transaction.id)
    )
    with get_session() as session:
        added = session.execute(stmt).scalars().all()
        session.commit()
    return len(added)


def latest_booking_dates(account_ids: list[uuid.UUID]) -> dict[uuid.UUID, date]:
    if not account_ids:
        return {}
    with get_session() as session:
        rows = session.execute(
            select(Transaction.account_id, func.max(Transaction.booking_date))
            .where(Transaction.account_id.in_(account_ids))
            .group_by(Transaction.account_id)
        ).all()
    return {account_id: latest for account_id, latest in rows}


def list_transactions(user_id: uuid.UUID, limit: int = 1000) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.execute(
            select(Transaction, BankAccount.name, BankConnection.bank)
            .join(BankAccount, Transaction.account_id == BankAccount.id)
            .join(BankConnection, BankAccount.connection_id == BankConnection.id)
            .where(BankConnection.user_id == user_id)
            .order_by(Transaction.booking_date.desc(), Transaction.created_at.desc())
            .limit(limit)
        ).all()
    return [
        {
            "id": str(tx.id),
            "date": tx.booking_date.isoformat(),
            "bank": bank,
            "accountName": account_name,
            "counterparty": tx.counterparty_name,
            "amount": str(tx.amount),
            "currency": tx.currency,
        }
        for tx, account_name, bank in rows
    ]

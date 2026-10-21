"""Bank connections and their accounts (Enable Banking sessions)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import Insert, insert

from app.config import settings
from app.database.engine import get_session
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.finance.enable_banking import EbAccount, EbSession
from app.finance.expiry import connection_status

BANKS: tuple[str, ...] = ("N26", "ING", "PayPal")
# Fixture data for the demo user: never synced, never expiring, never connected.
DEMO_BANK = "Demo Bank"


@dataclass(frozen=True)
class SyncAccount:
    id: uuid.UUID
    uid: str
    bank: str
    connection_id: uuid.UUID


@dataclass
class ConnectionState:
    id: uuid.UUID
    bank: str
    valid_until: datetime | None
    invalidated_at: datetime | None
    expiry_notice: str | None


class UnknownState(Exception):
    """No pending connection matches this user and state."""


def keep_accounts(bank: str, accounts: list[EbAccount]) -> list[EbAccount]:
    """N26 spaces have no IBAN; only the main account is wanted."""
    if bank == "N26":
        return [a for a in accounts if a.iban]
    return accounts


def mask_iban(iban: str | None) -> str | None:
    if not iban:
        return None
    return f"{iban[:4]} •••• {iban[-4:]}"


def account_upsert(connection_id: uuid.UUID, accounts: list[EbAccount]) -> Insert:
    """Insert accounts, updating in place on reconnect so account ids stay stable."""
    stmt = insert(BankAccount).values(
        [
            {
                "connection_id": connection_id,
                "uid": a.uid,
                "identification_hash": a.identification_hash,
                "iban": a.iban,
                "name": a.name,
                "currency": a.currency,
            }
            for a in accounts
        ]
    )
    return stmt.on_conflict_do_update(
        index_elements=["connection_id", "identification_hash"],
        set_={
            col: getattr(stmt.excluded, col)
            for col in ("uid", "iban", "name", "currency")
        },
    )


def rehash_by_iban(existing: list[BankAccount], incoming: list[EbAccount]) -> None:
    """Point an existing row at a new identification_hash when only the hash changed.

    The upsert matches on the hash, so without this a bank that re-issues hashes on
    reconnect would get a second account row and lose its transaction history.
    """
    hashes = {row.identification_hash for row in existing}
    for account in incoming:
        if account.identification_hash in hashes or not account.iban:
            continue
        for row in existing:
            if row.iban == account.iban:
                row.identification_hash = account.identification_hash
                hashes.add(account.identification_hash)
                break


def begin_connection(user_id: uuid.UUID, bank: str, state: str) -> None:
    """Record the one-time state; an active session_id on the row is left alone."""
    stmt = insert(BankConnection).values(
        user_id=user_id, bank=bank, pending_state=state
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "bank"],
        set_={"pending_state": state, "updated_at": func.now()},
    )
    with get_session() as session:
        session.execute(stmt)
        session.commit()


def find_pending(user_id: uuid.UUID, state: str) -> str | None:
    with get_session() as session:
        return session.scalar(
            select(BankConnection.bank).where(
                BankConnection.user_id == user_id,
                BankConnection.pending_state == state,
            )
        )


def complete_connection(user_id: uuid.UUID, state: str, session: EbSession) -> None:
    """Store the session and accounts, and clear the state so it cannot be replayed."""
    with get_session() as db:
        connection = db.scalar(
            select(BankConnection).where(
                BankConnection.user_id == user_id,
                BankConnection.pending_state == state,
            )
        )
        if connection is None:
            raise UnknownState(state)
        connection.session_id = session.session_id
        connection.valid_until = session.valid_until
        connection.pending_state = None
        connection.invalidated_at = None
        connection.expiry_notice = None
        accounts = keep_accounts(connection.bank, session.accounts)
        if accounts:
            existing = list(
                db.scalars(select(BankAccount).where(BankAccount.connection_id == connection.id))
            )
            rehash_by_iban(existing, accounts)
            db.flush()
            db.execute(account_upsert(connection.id, accounts))
        db.commit()


def clear_pending(user_id: uuid.UUID, state: str) -> None:
    with get_session() as session:
        session.execute(
            update(BankConnection)
            .where(
                BankConnection.user_id == user_id,
                BankConnection.pending_state == state,
            )
            .values(pending_state=None)
        )
        session.commit()


def list_connections(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """One entry per supported bank, in BANKS order, connected or not.

    The demo user sees only the Demo Bank.
    """
    with get_session() as session:
        connections = {
            c.bank: c
            for c in session.scalars(
                select(BankConnection).where(BankConnection.user_id == user_id)
            )
        }
        accounts: dict[uuid.UUID, list[BankAccount]] = {}
        if connections:
            for account in session.scalars(
                select(BankAccount)
                .where(
                    BankAccount.connection_id.in_([c.id for c in connections.values()])
                )
                .order_by(BankAccount.created_at, BankAccount.id)
            ):
                accounts.setdefault(account.connection_id, []).append(account)

    now = datetime.now(UTC)
    result: list[dict[str, Any]] = []
    banks = (DEMO_BANK,) if user_id == settings.demo_user_id else BANKS
    for bank in banks:
        connection = connections.get(bank)
        connected = connection is not None and connection.session_id is not None
        result.append(
            {
                "bank": bank,
                "connected": connected,
                "validUntil": (
                    connection.valid_until.isoformat()
                    if connected and connection.valid_until
                    else None
                ),
                "status": (
                    connection_status(connection.valid_until, connection.invalidated_at, now)
                    if connected
                    else None
                ),
                "accounts": [
                    {
                        "id": str(a.id),
                        "name": a.name,
                        "ibanMasked": mask_iban(a.iban),
                        "currency": a.currency,
                    }
                    for a in accounts.get(connection.id, [])
                ]
                if connected
                else [],
            }
        )
    return result


def sync_targets(user_id: uuid.UUID, now: datetime) -> tuple[list[SyncAccount], int]:
    """Accounts of live connections, and how many connections were skipped.

    An expired consent would only fail at the bank and spend an unattended read.
    """
    with get_session() as session:
        connections = list(
            session.scalars(
                select(BankConnection).where(
                    BankConnection.user_id == user_id, BankConnection.bank.in_(BANKS)
                )
            )
        )
        live = {
            c.id: c.bank
            for c in connections
            if c.session_id
            and connection_status(c.valid_until, c.invalidated_at, now) != "expired"
        }
        accounts = (
            list(
                session.scalars(
                    select(BankAccount)
                    .where(BankAccount.connection_id.in_(live))
                    .order_by(BankAccount.created_at, BankAccount.id)
                )
            )
            if live
            else []
        )
    return (
        [
            SyncAccount(
                id=a.id, uid=a.uid, bank=live[a.connection_id], connection_id=a.connection_id
            )
            for a in accounts
        ],
        len(connections) - len(live),
    )


def connection_states(user_id: uuid.UUID) -> list[ConnectionState]:
    """Every connection that has had a session, for expiry warnings."""
    with get_session() as session:
        return [
            ConnectionState(
                id=c.id,
                bank=c.bank,
                valid_until=c.valid_until,
                invalidated_at=c.invalidated_at,
                expiry_notice=c.expiry_notice,
            )
            for c in session.scalars(
                select(BankConnection).where(
                    BankConnection.user_id == user_id,
                    BankConnection.bank.in_(BANKS),
                    BankConnection.session_id.is_not(None),
                )
            )
        ]


def mark_invalid(connection_id: uuid.UUID, now: datetime) -> None:
    with get_session() as session:
        session.execute(
            update(BankConnection)
            .where(BankConnection.id == connection_id)
            .values(invalidated_at=now)
        )
        session.commit()


def record_notice(connection_id: uuid.UUID, stage: str) -> None:
    with get_session() as session:
        session.execute(
            update(BankConnection)
            .where(BankConnection.id == connection_id)
            .values(expiry_notice=stage)
        )
        session.commit()

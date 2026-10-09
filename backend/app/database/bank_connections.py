"""Bank connections and their accounts (Enable Banking sessions)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import Insert, insert

from app.database.engine import get_session
from app.database.models.finance.bank_account import BankAccount
from app.database.models.finance.bank_connection import BankConnection
from app.finance.enable_banking import EbAccount, EbSession

BANKS: tuple[str, ...] = ("N26", "ING", "PayPal")


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
        accounts = keep_accounts(connection.bank, session.accounts)
        if accounts:
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
    """One entry per supported bank, in BANKS order, connected or not."""
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

    result: list[dict[str, Any]] = []
    for bank in BANKS:
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

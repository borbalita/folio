"""Return the demo user's Finance to the base state. Run from backend/: uv run python -m app.demo.reset"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.engine import get_session
from app.database.models.chat.thread import ChatThread
from app.database.models.email.message import EmailMessage
from app.database.models.finance.transaction import Transaction
from app.database.models.user import User
from app.demo.accounts import ensure_demo_accounts
from app.demo.base_state import build_base_state
from app.logging import configure_logging


def reset_demo(
    session: Session, user_id: uuid.UUID, *, email: str, today: date
) -> dict[str, int]:
    """Delete the demo user's Finance rows and write the base state; the caller commits.

    Invoices, matches, payment drafts, attachments and chunks go with their email, and
    chat messages with their thread, through the database's cascades.
    """
    accounts = ensure_demo_accounts(session, user_id)
    session.execute(
        delete(EmailMessage).where(EmailMessage.mailbox_id == accounts.mailbox_id)
    )
    session.execute(
        delete(Transaction).where(Transaction.account_id == accounts.account_id)
    )
    session.execute(
        delete(ChatThread).where(
            ChatThread.user_id == user_id, ChatThread.agent == "finance"
        )
    )
    rows = build_base_state(today, accounts, to_address=email)
    # No relationships are mapped, so the unit of work doesn't know parents from
    # children; flushing one table at a time keeps the foreign keys satisfied.
    for group in rows.groups():
        session.add_all(group)
        session.flush()
    return {"invoices": len(rows.invoices), "transactions": len(rows.transactions)}


def run_reset(
    user_id: uuid.UUID, email: str, today: date | None = None
) -> dict[str, int]:
    """Reset in one transaction: an error closes the session uncommitted, so nothing changes."""
    today = today or datetime.now(ZoneInfo(settings.email_timezone)).date()
    with get_session() as session:
        counts = reset_demo(session, user_id, email=email, today=today)
        session.commit()
    return counts


def demo_user_email(user_id: uuid.UUID) -> str | None:
    with get_session() as session:
        return session.scalar(select(User.email).where(User.id == user_id))


def main() -> int:
    configure_logging()
    user_id = settings.demo_user_id
    if user_id is None:
        print("Set DEMO_USER_ID first.", file=sys.stderr)
        return 1
    email = demo_user_email(user_id)
    if email is None:
        # The users row appears on the first sign-in; the demo rows need it.
        print("Sign in once as the demo user first.", file=sys.stderr)
        return 1
    counts = run_reset(user_id, email)
    print(", ".join(f"{name}: {value}" for name, value in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

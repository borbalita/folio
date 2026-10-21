"""Finance is open to the owner and the demo user named in settings; off when neither is set."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import HTTPException, status

from app.auth.dependencies import CurrentUser
from app.config import settings
from app.database import mailboxes


def is_finance_user(user: CurrentUser) -> bool:
    return user.id in (settings.finance_owner_user_id, settings.demo_user_id)


def require_finance_user(user: CurrentUser) -> None:
    if not is_finance_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def require_invoice_mailboxes(user: CurrentUser) -> list[uuid.UUID]:
    """The user's active mailbox ids for invoices, demo included; 403 when there are none."""
    ids = await asyncio.to_thread(mailboxes.invoice_mailbox_ids, user.id)
    if not ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return ids

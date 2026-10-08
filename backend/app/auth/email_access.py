"""Email routes are limited to users who own an active mailbox."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import HTTPException, status

from app.auth.dependencies import CurrentUser
from app.auth.finance_access import is_finance_owner, require_finance_owner
from app.database import mailboxes


async def require_email_access(user: CurrentUser) -> list[uuid.UUID]:
    """The user's active mailbox ids; 403 when there are none."""
    ids = await asyncio.to_thread(mailboxes.active_mailbox_ids, user.id)
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return ids


async def agents_for(user: CurrentUser) -> list[str]:
    agents = ["documents"]
    ids = await asyncio.to_thread(mailboxes.active_mailbox_ids, user.id)
    if ids:
        agents.append("email")
    if is_finance_owner(user):
        agents.append("finance")
    return agents


async def require_agent_access(user: CurrentUser, agent: str) -> None:
    """The one access rule for an agent's threads and streams."""
    if agent == "email":
        await require_email_access(user)
    elif agent == "finance":
        require_finance_owner(user)

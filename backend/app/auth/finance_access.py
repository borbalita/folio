"""Finance is open to the owner and the demo user named in settings; off when neither is set."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.auth.dependencies import CurrentUser
from app.config import settings


def is_finance_user(user: CurrentUser) -> bool:
    return user.id in (settings.finance_owner_user_id, settings.demo_user_id)


def require_finance_user(user: CurrentUser) -> None:
    if not is_finance_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

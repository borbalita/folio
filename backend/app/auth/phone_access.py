"""Phone calls cost per minute, so they follow the Finance rule: the owner and the demo user."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.auth.dependencies import CurrentUser
from app.auth.finance_access import is_finance_user


def is_phone_user(user: CurrentUser) -> bool:
    return is_finance_user(user)


def require_phone_user(user: CurrentUser) -> None:
    if not is_phone_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

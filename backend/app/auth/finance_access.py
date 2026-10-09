"""Finance is limited to the one user named in settings; off for everyone when unset."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.auth.dependencies import CurrentUser
from app.config import settings


def is_finance_owner(user: CurrentUser) -> bool:
    owner = settings.finance_owner_user_id
    return owner is not None and user.id == owner


def require_finance_owner(user: CurrentUser) -> None:
    if not is_finance_owner(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

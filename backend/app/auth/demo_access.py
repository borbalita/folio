"""Demo routes belong to the one demo user; they do not exist while it is unset."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import CurrentUser, get_current_user
from app.config import settings


def is_demo_user(user_id: uuid.UUID) -> bool:
    return settings.demo_user_id is not None and user_id == settings.demo_user_id


def require_demo_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if settings.demo_user_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not is_demo_user(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user

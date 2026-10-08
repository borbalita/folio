"""Finance routes. Every route is owner-only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.finance_access import require_finance_owner


def finance_owner(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    require_finance_owner(user)
    return user


router = APIRouter(
    prefix="/finance", tags=["finance"], dependencies=[Depends(finance_owner)]
)


@router.get("/access")
async def access() -> dict[str, bool]:
    """Lets the Finance area confirm the caller is the owner."""
    return {"owner": True}

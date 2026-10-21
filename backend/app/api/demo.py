"""Presenter routes for the demo. Only the demo user; 404 while DEMO_USER_ID is unset."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.demo_access import require_demo_user
from app.auth.dependencies import CurrentUser
from app.demo import booking

router = APIRouter(prefix="/finance/demo", tags=["demo"])


@router.get("/payments")
async def list_payments(
    user: Annotated[CurrentUser, Depends(require_demo_user)],
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(booking.approved_payments, user.id)


@router.post("/payments/{payment_id}/book")
async def book_payment(
    payment_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_demo_user)],
) -> dict[str, Any]:
    return await asyncio.to_thread(booking.book, user.id, payment_id)

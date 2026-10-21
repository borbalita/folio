"""Presenter routes for the demo. Only the demo user; 404 while DEMO_USER_ID is unset."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.demo_access import require_demo_user
from app.auth.dependencies import CurrentUser
from app.database import chats
from app.demo import booking, live

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


class NewInvoice(BaseModel):
    kind: live.RequestedKind


@router.post("/invoices")
async def send_invoice(
    body: NewInvoice,
    user: Annotated[CurrentUser, Depends(require_demo_user)],
) -> dict[str, Any]:
    """Waits for the real models (about 10–20 s) and returns what was stored."""
    # Auth writes only auth.users; the demo mailbox needs the app's users row.
    await asyncio.to_thread(chats.ensure_user, user.id, user.email)
    return await asyncio.to_thread(live.send_invoice, user.id, body.kind)

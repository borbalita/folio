"""Finance routes. Every route is owner-only."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.email_access import require_email_access
from app.auth.finance_access import require_finance_owner
from app.database import invoices


def finance_owner(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    require_finance_owner(user)
    return user


router = APIRouter(
    prefix="/finance", tags=["finance"], dependencies=[Depends(finance_owner)]
)

# Invoice data stays scoped to the owner's mailboxes, so each route resolves them
# after the router-level owner check.


@router.get("/invoices")
async def list_invoices(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    mailbox_ids = await require_email_access(user)
    return await asyncio.to_thread(invoices.list_invoices, mailbox_ids)


@router.get("/invoices/{email_id}")
async def get_invoice(
    email_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_email_access(user)
    return await asyncio.to_thread(invoices.get_invoice, email_id, mailbox_ids)


@router.get("/attachments/{attachment_id}")
async def get_attachment(
    attachment_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    mailbox_ids = await require_email_access(user)
    file = await asyncio.to_thread(
        invoices.get_attachment_file, attachment_id, mailbox_ids
    )
    return Response(
        content=file.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(file.filename)}",
            "Cache-Control": "private, no-store",
        },
    )

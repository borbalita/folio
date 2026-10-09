"""Finance routes. Every route is owner-only."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from typing import Annotated, Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.email_access import require_email_access
from app.auth.finance_access import require_finance_owner
from app.database import bank_connections, invoices
from app.finance import enable_banking

log = structlog.get_logger(__name__)


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


class CallbackBody(BaseModel):
    code: str
    state: str


def _unknown_attempt() -> HTTPException:
    return HTTPException(400, "Unknown or expired connection attempt.")


@router.get("/bank-connections")
async def list_bank_connections(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(bank_connections.list_connections, user.id)


@router.post("/bank-connections/callback")
async def bank_connection_callback(
    body: CallbackBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    # Checked before any bank call so a forged or replayed state costs nothing.
    pending = await asyncio.to_thread(
        bank_connections.find_pending, user.id, body.state
    )
    if pending is None:
        raise _unknown_attempt()
    try:
        session = await enable_banking.create_session(body.code)
    except enable_banking.EnableBankingError as exc:
        log.warning("bank_connection_rejected", status=exc.status, body=exc.body)
        await asyncio.to_thread(bank_connections.clear_pending, user.id, body.state)
        raise HTTPException(502, "Bank connection failed; start it again.") from exc
    try:
        await asyncio.to_thread(
            bank_connections.complete_connection, user.id, body.state, session
        )
    except bank_connections.UnknownState as exc:
        raise _unknown_attempt() from exc
    return await asyncio.to_thread(bank_connections.list_connections, user.id)


@router.post("/bank-connections/{bank}/start")
async def start_bank_connection(
    bank: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    if bank not in bank_connections.BANKS:
        raise HTTPException(404, "Unknown bank.")
    state = secrets.token_urlsafe(32)
    await asyncio.to_thread(bank_connections.begin_connection, user.id, bank, state)
    try:
        url = await enable_banking.start_authorization(bank, state)
    except enable_banking.EnableBankingNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except enable_banking.EnableBankingError as exc:
        log.warning("bank_start_failed", bank=bank, status=exc.status, body=exc.body)
        # A 4xx means the bank was reached and refused; only the owner can fix the settings.
        if 400 <= exc.status < 500:
            raise HTTPException(
                502,
                "Enable Banking refused the request; "
                "check the application's redirect URLs and settings.",
            ) from exc
        raise HTTPException(502, "Could not reach the bank; try again.") from exc
    return {"url": url}

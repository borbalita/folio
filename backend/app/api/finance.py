"""Finance routes. Every route is for the Finance owner or the demo user."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.auth.demo_access import is_demo_user
from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.finance_access import require_finance_user, require_invoice_mailboxes
from app.database import (
    bank_connections,
    invoices,
    job_runs,
    matches,
    payments,
    transactions,
)
from app.finance import enable_banking, transaction_sync

log = structlog.get_logger(__name__)


def finance_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    require_finance_user(user)
    return user


SYNC_COOLDOWN = timedelta(minutes=10)

router = APIRouter(
    prefix="/finance", tags=["finance"], dependencies=[Depends(finance_user)]
)

# Invoice data stays scoped to the owner's mailboxes, so each route resolves them
# after the router-level Finance access check.


@router.get("/invoices")
async def list_invoices(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(invoices.list_invoices, mailbox_ids)


@router.get("/invoices/{email_id}")
async def get_invoice(
    email_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(invoices.get_invoice, email_id, mailbox_ids)


@router.get("/attachments/{attachment_id}")
async def get_attachment(
    attachment_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    mailbox_ids = await require_invoice_mailboxes(user)
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


class InvoiceEdit(BaseModel):
    """Fields the owner changes; only the ones sent are touched. Null clears a field."""

    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")

    payee: str | None = None
    iban: str | None = None
    bic: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    invoice_number: str | None = None
    reference: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None


class InvoicesPaid(BaseModel):
    ids: list[uuid.UUID]
    paid: bool


@router.patch("/invoices/items/{invoice_id}")
async def update_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceEdit,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    changes = body.model_dump(exclude_unset=True)
    await asyncio.to_thread(invoices.update_invoice, invoice_id, changes, mailbox_ids)
    # An edited amount, IBAN or reference can make or break a match.
    await asyncio.to_thread(matches.match_for_user, user.id)
    return await asyncio.to_thread(invoices.get_invoice_item, invoice_id, mailbox_ids)


@router.post("/invoices/items/paid")
async def set_invoices_paid(
    body: InvoicesPaid,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(
        invoices.set_invoices_paid, body.ids, body.paid, mailbox_ids
    )


@router.post("/matches/{match_id}/confirm")
async def confirm_match(
    match_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    invoice_id = await asyncio.to_thread(matches.confirm, match_id, mailbox_ids)
    return await asyncio.to_thread(invoices.get_invoice_item, invoice_id, mailbox_ids)


@router.post("/matches/{match_id}/reject")
async def reject_match(
    match_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    invoice_id = await asyncio.to_thread(matches.reject, match_id, mailbox_ids)
    return await asyncio.to_thread(invoices.get_invoice_item, invoice_id, mailbox_ids)


class DraftsRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")

    invoice_ids: list[uuid.UUID]


@router.post("/payment-drafts")
async def create_payment_drafts(
    body: DraftsRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(
        payments.create_drafts, body.invoice_ids, mailbox_ids
    )


@router.get("/payment-drafts")
async def get_payment_drafts(
    ids: Annotated[list[uuid.UUID], Query()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(payments.get_drafts, ids, mailbox_ids)


@router.post("/payment-drafts/{draft_id}/approve")
async def approve_payment_draft(
    draft_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(payments.approve, draft_id, mailbox_ids)


@router.post("/payment-drafts/{draft_id}/cancel")
async def cancel_payment_draft(
    draft_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    mailbox_ids = await require_invoice_mailboxes(user)
    return await asyncio.to_thread(payments.cancel, draft_id, mailbox_ids)


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
    if is_demo_user(user.id):
        raise HTTPException(403, "The demo bank cannot be connected.")
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
    if is_demo_user(user.id):
        raise HTTPException(403, "The demo bank cannot be connected.")
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


def _psu_headers(request: Request) -> dict[str, str]:
    """Tell the bank the owner is present, so Sync now spends no unattended read."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else None
    if not ip and request.client:
        ip = request.client.host
    headers = {"Psu-User-Agent": request.headers.get("user-agent", "")}
    if ip:
        headers["Psu-Ip-Address"] = ip
    return headers


@router.post("/bank-sync")
async def sync_banks(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, int]:
    if is_demo_user(user.id):
        # Nothing to fetch, and a demo press must neither hit nor start the owner's cooldown.
        return {"accounts": 0, "fetched": 0, "added": 0, "skipped": 0, "unparsed": 0}
    last = await asyncio.to_thread(job_runs.last_started, "bank_sync")
    if last is not None and datetime.now(UTC) - last < SYNC_COOLDOWN:
        raise HTTPException(429, "Synced less than 10 minutes ago; try again later.")
    try:
        return await asyncio.to_thread(
            transaction_sync.run_bank_sync, user.id, _psu_headers(request)
        )
    except enable_banking.EnableBankingNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except transaction_sync.BankSyncFailed as exc:
        raise HTTPException(
            502, "Some banks could not be synced; see the job log."
        ) from exc


@router.get("/transactions")
async def list_transactions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(transactions.list_transactions, user.id)

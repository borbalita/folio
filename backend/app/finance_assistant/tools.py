"""Finance agent tools. They read, or prepare payment drafts; none approves or pays."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic_ai import RunContext

from app.database import bank_connections, invoices, payments, transactions
from app.finance_assistant.deps import FinanceAgentDeps

LOOKING = "Looking at your finances"
InvoiceStatus = Literal["open", "needs_info", "paid"]


async def _status(deps: FinanceAgentDeps) -> None:
    if deps.status_queue is not None:
        await deps.status_queue.put(LOOKING)


def _amount(row: dict[str, Any]) -> str:
    if row.get("amount") is None:
        return "amount unknown"
    return f"{row['amount']} {row.get('currency') or ''}".strip()


def _invoice_line(row: dict[str, Any]) -> str:
    return (
        f"[{row['id']}] {row.get('payee') or 'unknown payee'}, {_amount(row)}, "
        f"due {row.get('dueDate') or 'unknown'}, status {row['status']}, "
        f"reference {row.get('reference') or row.get('invoiceNumber') or 'none'}"
    )


def execute_list_invoices(deps: FinanceAgentDeps, status: InvoiceStatus | None) -> str:
    rows = [
        row
        for row in invoices.list_invoices(deps.mailbox_ids)
        if status is None or row["status"] == status
    ]
    if not rows:
        return "No invoices found."
    deps.seen_invoice_ids.update(UUID(row["id"]) for row in rows)
    return "\n".join(_invoice_line(row) for row in rows)


def execute_get_invoice(deps: FinanceAgentDeps, invoice_id: UUID) -> str:
    # The model can pass a mistyped or invented id; tell it, rather than failing the turn.
    try:
        row = invoices.get_invoice_item(invoice_id, deps.mailbox_ids)
    except HTTPException:
        return f"Invoice {invoice_id} was not found. List the invoices to get valid ids."
    deps.seen_invoice_ids.add(UUID(row["id"]))
    return f"{_invoice_line(row)}, IBAN {row.get('iban') or 'unknown'}"


def execute_search_transactions(
    deps: FinanceAgentDeps,
    text: str | None,
    since: date | None,
    until: date | None,
    limit: int,
) -> str:
    rows = transactions.search_transactions(
        deps.user_id, text=text, since=since, until=until, limit=limit
    )
    if not rows:
        return "No transactions found."
    return "\n".join(
        f"{row['date']} {row['bank']}: {row.get('counterparty') or 'unknown'}, "
        f"{row['amount']} {row['currency']}, {row.get('remittance') or ''}".rstrip(", ")
        for row in rows
    )


def execute_list_accounts(deps: FinanceAgentDeps) -> str:
    lines = []
    for connection in bank_connections.list_connections(deps.user_id):
        if not connection["connected"]:
            lines.append(f"{connection['bank']}: not connected")
            continue
        until = (connection.get("validUntil") or "")[:10] or "unknown"
        lines.append(
            f"{connection['bank']}: connected, {connection['status']}, valid until {until}"
        )
    return "\n".join(lines)


def execute_prepare_payments(deps: FinanceAgentDeps, invoice_ids: list[UUID]) -> str:
    try:
        result = payments.create_drafts(invoice_ids, deps.mailbox_ids)
    except HTTPException:
        return (
            "No payments were prepared: at least one invoice id was not found. "
            "List the open invoices and use their ids."
        )
    deps.seen_draft_ids.update(UUID(draft["id"]) for draft in result["drafts"])
    lines = [
        f"Prepared [{draft['id']}] for invoice {draft['invoiceId']}: "
        f"{draft.get('payee') or 'unknown payee'}, {_amount(draft)}"
        for draft in result["drafts"]
    ]
    lines += [
        f"Skipped invoice {skip['invoiceId']}: {skip['reason']}" for skip in result["skipped"]
    ]
    if result["drafts"]:
        lines.append("These payments await the owner's approval on their cards.")
    else:
        lines.append("No payments were prepared.")
    return "\n".join(lines)


async def list_invoices(
    ctx: RunContext[FinanceAgentDeps], status: InvoiceStatus | None = None
) -> str:
    """The owner's invoices, newest first; optionally only open, needs_info or paid."""
    await _status(ctx.deps)
    return await asyncio.to_thread(execute_list_invoices, ctx.deps, status)


async def get_invoice(ctx: RunContext[FinanceAgentDeps], invoice_id: UUID) -> str:
    """One invoice by id, with its IBAN."""
    await _status(ctx.deps)
    return await asyncio.to_thread(execute_get_invoice, ctx.deps, invoice_id)


async def search_transactions(
    ctx: RunContext[FinanceAgentDeps],
    text: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 20,
) -> str:
    """Bank transactions, newest first; text matches counterparty or remittance."""
    await _status(ctx.deps)
    return await asyncio.to_thread(
        execute_search_transactions, ctx.deps, text, since, until, min(limit, 100)
    )


async def list_accounts(ctx: RunContext[FinanceAgentDeps]) -> str:
    """The connected banks and how long their access lasts."""
    await _status(ctx.deps)
    return await asyncio.to_thread(execute_list_accounts, ctx.deps)


async def prepare_payments(ctx: RunContext[FinanceAgentDeps], invoice_ids: list[UUID]) -> str:
    """Prepare payment drafts for these invoices. The owner approves each one; this doesn't."""
    await _status(ctx.deps)
    return await asyncio.to_thread(execute_prepare_payments, ctx.deps, invoice_ids)

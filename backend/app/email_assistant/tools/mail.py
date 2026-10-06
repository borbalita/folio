"""search_emails for the email agent."""

from __future__ import annotations

import asyncio
from datetime import date

from pydantic_ai import RunContext

from app.database import mailboxes
from app.database.models.email.message import EmailLabel
from app.email_assistant.deps import EmailAgentDeps
from app.email_assistant.tools.status import emit_status
from app.retrieval.email.formatting import format_email_passages
from app.retrieval.email.queries import EmailSearchFilters

SEARCHING_MAIL = "Searching your mail"


async def search_emails(
    ctx: RunContext[EmailAgentDeps],
    query: str,
    since: date | None = None,
    until: date | None = None,
    label: EmailLabel | None = None,
    sender: str | None = None,
    mailbox: str | None = None,
) -> str:
    """Search the user's mail. Optional since, until, label, sender, and mailbox."""
    await emit_status(ctx.deps, SEARCHING_MAIL)
    return await asyncio.to_thread(
        execute_search_emails,
        ctx.deps,
        query,
        question=ctx.prompt if isinstance(ctx.prompt, str) else None,
        since=since,
        until=until,
        label=label,
        sender=sender,
        mailbox=mailbox,
    )


def execute_search_emails(
    deps: EmailAgentDeps,
    query: str,
    *,
    question: str | None = None,
    since: date | None = None,
    until: date | None = None,
    label: EmailLabel | None = None,
    sender: str | None = None,
    mailbox: str | None = None,
) -> str:
    filters = EmailSearchFilters(
        user_id=deps.user_id,
        mailbox_ids=mailboxes.active_mailbox_ids(deps.user_id),
        since=since,
        until=until,
        label=label,
        sender=sender,
        mailbox=mailbox,
    )
    passages = deps.retriever.search(query, filters=filters, question=question)
    for passage in passages:
        deps.remember(passage.chunk_id, passage)
    return format_email_passages(passages)

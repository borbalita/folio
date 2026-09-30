"""search_emails for the email agent."""

from __future__ import annotations

from datetime import date

from app.database import mailboxes
from app.database.models.email.message import EmailLabel
from app.email_assistant.deps import EmailAgentDeps
from app.retrieval.email.formatting import format_email_passages
from app.retrieval.email.queries import EmailSearchFilters


def execute_search_emails(
    deps: EmailAgentDeps,
    query: str,
    *,
    since: date | None = None,
    until: date | None = None,
    label: str | None = None,
    sender: str | None = None,
    mailbox: str | None = None,
) -> str:
    mailbox_ids = mailboxes.active_mailbox_ids(deps.user_id)
    filters = EmailSearchFilters(
        user_id=deps.user_id,
        mailbox_ids=mailbox_ids,
        since=since,
        until=until,
        label=label,
        sender=sender,
        mailbox=mailbox,
    )
    passages = deps.retriever.search(query, filters=filters)
    for passage in passages:
        deps.seen_ids.add(passage.chunk_id)
        deps.seen_passages[passage.chunk_id] = passage
    return format_email_passages(passages)


def parse_label(label: str | None) -> str | None:
    if label is None or not label.strip():
        return None
    try:
        return EmailLabel(label.strip()).value
    except ValueError:
        return None

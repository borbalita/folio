"""Status updates shared by the mail and news tools."""

from __future__ import annotations

from app.email_assistant.deps import EmailAgentDeps


async def emit_status(deps: EmailAgentDeps, label: str) -> None:
    if deps.status_queue is not None:
        await deps.status_queue.put(label)

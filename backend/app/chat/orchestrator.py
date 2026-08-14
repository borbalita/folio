"""Coordinates one chat turn. Stub: canned streamed reply, then persist."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from app.auth.dependencies import CurrentUser
from app.chat.messages import (
    assistant_message_for_storage,
    extract_latest_user_text,
    user_message_for_storage,
)
from app.chat.streaming import iter_canned_text_stream
from app.database import chats


def build_stub_reply(user_text: str) -> str:
    if user_text:
        return (
            "Document Copilot stub reply. "
            f"You asked: {user_text} "
            "(Retrieval and grounded answers come in a later step.)"
        )
    return (
        "Document Copilot stub reply. "
        "Send a user message to see an echo. "
        "(Retrieval and grounded answers come in a later step.)"
    )


async def run_stub_turn(
    user: CurrentUser,
    thread_id: uuid.UUID,
    messages: list[dict],
) -> AsyncIterator[str]:
    """Stream a canned reply, then persist user + assistant messages on success."""
    await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    await asyncio.to_thread(chats.ensure_user, user.id, user.email)

    user_text = extract_latest_user_text(messages)
    reply = build_stub_reply(user_text)

    async for frame in iter_canned_text_stream(reply):
        yield frame

    await asyncio.to_thread(
        chats.append_messages,
        thread_id,
        [
            {"role": "user", "message": user_message_for_storage(messages)},
            {"role": "assistant", "message": assistant_message_for_storage(reply)},
        ],
    )

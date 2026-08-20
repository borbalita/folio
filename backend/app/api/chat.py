"""Chat thread and streaming routes."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth.dependencies import CurrentUser, get_current_user
from app.chat.messages import CreateThreadRequest, StreamChatRequest
from app.chat.orchestrator import run_stub_turn
from app.database import chats

router = APIRouter(tags=["chat"])


@router.post("/threads")
async def create_thread(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    body: CreateThreadRequest | None = None,
) -> dict[str, Any]:
    title = body.title if body else None
    return await asyncio.to_thread(
        chats.create_thread_for_user, user.id, user.email, title
    )


@router.get("/threads")
async def list_threads(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(chats.list_threads, user.id)


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    return await asyncio.to_thread(chats.list_messages, thread_id)


@router.post("/chat/stream")
async def chat_stream(
    body: StreamChatRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    # Ownership check before opening the stream so clients get HTTP 403/404,
    # not a mid-stream error frame.
    await asyncio.to_thread(chats.get_thread_for_user, body.thread_id, user.id)

    return StreamingResponse(
        run_stub_turn(user, body.thread_id, body.messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-vercel-ai-ui-message-stream": "v1",
        },
    )

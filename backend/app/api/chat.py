"""Chat thread and streaming routes."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.email_access import require_agent_access, require_news_access
from app.chat.messages import AgentName, CreateThreadRequest, StreamChatRequest
from app.chat.orchestrator import run_turn
from app.database import chats, news_story

router = APIRouter(tags=["chat"])


@router.post("/threads")
async def create_thread(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    body: CreateThreadRequest | None = None,
) -> dict[str, Any]:
    title = body.title if body else None
    agent = body.agent if body else "documents"
    await require_agent_access(user, agent)
    story_items = await _checked_story_items(user, body, agent)
    return await asyncio.to_thread(
        chats.create_thread_for_user, user.id, user.email, title, agent, story_items
    )


async def _checked_story_items(
    user: CurrentUser, body: CreateThreadRequest | None, agent: str
) -> list[dict[str, Any]] | None:
    """The refs to store, once they are known to be items of the user's own newsletters."""
    if body is None or body.story_items is None:
        return None
    if agent != "news":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="story_items are only for news threads",
        )
    mailbox_ids = await require_news_access(user)
    refs = [(ref.email_id, ref.position) for ref in body.story_items]
    if not await asyncio.to_thread(news_story.owns_all, mailbox_ids, refs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown story")
    return [ref.model_dump(mode="json") for ref in body.story_items]


@router.get("/threads")
async def list_threads(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    agent: Annotated[AgentName, Query()] = "documents",
) -> list[dict[str, Any]]:
    await require_agent_access(user, agent)
    return await asyncio.to_thread(chats.list_threads, user.id, agent)


@router.delete("/threads/{thread_id}")
async def delete_empty_thread(
    thread_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, bool]:
    thread = await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    await require_agent_access(user, thread.get("agent"))
    deleted = await asyncio.to_thread(chats.delete_thread_if_empty, thread_id, user.id)
    return {"deleted": deleted}


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    thread = await asyncio.to_thread(chats.get_thread_for_user, thread_id, user.id)
    await require_agent_access(user, thread.get("agent"))
    return await asyncio.to_thread(chats.list_messages, thread_id)


@router.post("/chat/stream")
async def chat_stream(
    body: StreamChatRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    thread = await asyncio.to_thread(chats.get_thread_for_user, body.thread_id, user.id)
    await require_agent_access(user, thread.get("agent"))
    return StreamingResponse(
        run_turn(user, body.thread_id, body.messages, thread=thread),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-vercel-ai-ui-message-stream": "v1",
        },
    )

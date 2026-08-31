"""Chat thread and message persistence via the Supabase service-role client."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from app.database.supabase import get_admin_client

DEFAULT_THREAD_TITLE = "New chat"


def ensure_user(user_id: uuid.UUID, email: str) -> None:
    """Upsert a public.users row so chat FKs succeed (Auth only writes auth.users)."""
    get_admin_client().table("users").upsert(
        {"id": str(user_id), "email": email},
        on_conflict="id",
    ).execute()


def _thread_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _message_row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role": row["role"],
        "message": row["message"],
        "sequenceNumber": row["sequence_number"],
        "createdAt": row["created_at"],
    }


def create_thread_for_user(
    user_id: uuid.UUID, email: str, title: str | None = None
) -> dict[str, Any]:
    ensure_user(user_id, email)
    result = (
        get_admin_client()
        .table("chat_threads")
        .insert(
            {
                "id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "title": title or DEFAULT_THREAD_TITLE,
            }
        )
        .execute()
    )
    return _thread_row_to_api(result.data[0])


def list_threads(user_id: uuid.UUID) -> list[dict[str, Any]]:
    result = (
        get_admin_client()
        .table("chat_threads")
        .select("id, title, created_at, updated_at")
        .eq("user_id", str(user_id))
        .order("updated_at", desc=True)
        .execute()
    )
    return [_thread_row_to_api(row) for row in result.data]


def get_thread_for_user(thread_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    result = (
        get_admin_client()
        .table("chat_threads")
        .select("id, user_id, title, created_at, updated_at")
        .eq("id", str(thread_id))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    row = result.data[0]
    if row["user_id"] != str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return _thread_row_to_api(row)


def list_messages(thread_id: uuid.UUID) -> list[dict[str, Any]]:
    result = (
        get_admin_client()
        .table("chat_messages")
        .select("id, role, message, sequence_number, created_at")
        .eq("thread_id", str(thread_id))
        .order("sequence_number")
        .execute()
    )
    return [_message_row_to_api(row) for row in result.data]


def _next_sequence_number(thread_id: uuid.UUID) -> int:
    result = (
        get_admin_client()
        .table("chat_messages")
        .select("sequence_number")
        .eq("thread_id", str(thread_id))
        .order("sequence_number", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return 1
    return int(result.data[0]["sequence_number"]) + 1


def append_messages(
    thread_id: uuid.UUID,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert messages with consecutive sequence numbers; bump thread updated_at."""
    if not messages:
        return []

    seq = _next_sequence_number(thread_id)
    rows = []
    for item in messages:
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "thread_id": str(thread_id),
                "role": item["role"],
                "message": item["message"],
                "sequence_number": seq,
            }
        )
        seq += 1

    result = get_admin_client().table("chat_messages").insert(rows).execute()
    get_admin_client().table("chat_threads").update(
        {"updated_at": datetime.now(UTC).isoformat()}
    ).eq("id", str(thread_id)).execute()

    return [_message_row_to_api(row) for row in result.data]


def update_thread_title(thread_id: uuid.UUID, title: str) -> None:
    get_admin_client().table("chat_threads").update({"title": title}).eq("id", str(thread_id)).execute()


def insert_citations(
    message_id: uuid.UUID,
    citations: list[dict[str, Any]],
) -> None:
    if not citations:
        return

    rows = [
        {
            "id": str(uuid.uuid4()),
            "message_id": str(message_id),
            "chunk_id": str(item["chunk_id"]),
            "citation_index": item["citation_index"],
            "excerpt": item.get("excerpt"),
        }
        for item in citations
    ]
    get_admin_client().table("message_citations").insert(rows).execute()

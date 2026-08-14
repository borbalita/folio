"""AI SDK UI message wire format helpers for the chat stub."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StreamChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: uuid.UUID = Field(alias="threadId")
    messages: list[dict[str, Any]] = Field(default_factory=list)


class CreateThreadRequest(BaseModel):
    title: str | None = None


def extract_latest_user_text(messages: list[dict[str, Any]]) -> str:
    """Pull plain text from the last user message (AI SDK UI message shape)."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        parts = message.get("parts")
        if isinstance(parts, list):
            texts: list[str] = []
            for part in parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
            if texts:
                return "\n".join(texts)

        # Fallback: stringify remaining payload
        return str(content or message)

    return ""


def user_message_for_storage(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message
    return {"role": "user", "content": ""}


def assistant_message_for_storage(text: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": text,
        "parts": [{"type": "text", "text": text}],
    }

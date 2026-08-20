"""SSE helpers for AI SDK UI message stream protocol (v1).

Vercel AI SDK DefaultChatTransport expects Server-Sent Events:

    data: {"type":"start"}
    data: {"type":"start-step"}
    data: {"type":"text-start","id":"..."}
    data: {"type":"text-delta","id":"...","delta":"..."}
    data: {"type":"text-end","id":"..."}
    data: {"type":"finish-step"}
    data: {"type":"finish"}
    data: [DONE]

and the response header ``x-vercel-ai-ui-message-stream: v1``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable

TEXT_PART_ID = "text-1"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def format_stream_start() -> str:
    return _sse({"type": "start"})


def format_start_step() -> str:
    return _sse({"type": "start-step"})


def format_text_start(text_id: str = TEXT_PART_ID) -> str:
    return _sse({"type": "text-start", "id": text_id})


def format_text_delta(delta: str, text_id: str = TEXT_PART_ID) -> str:
    return _sse({"type": "text-delta", "id": text_id, "delta": delta})


def format_text_end(text_id: str = TEXT_PART_ID) -> str:
    return _sse({"type": "text-end", "id": text_id})


def format_finish_step() -> str:
    return _sse({"type": "finish-step"})


def format_stream_finish() -> str:
    return _sse({"type": "finish"})


def format_done() -> str:
    return "data: [DONE]\n\n"


def format_error(message: str) -> str:
    return _sse({"type": "error", "errorText": message})


def chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + size] for i in range(0, len(text), size)]


async def iter_canned_text_stream(text: str) -> AsyncIterator[str]:
    """Yield SSE frames for a canned assistant reply."""
    yield format_stream_start()
    yield format_start_step()
    yield format_text_start()
    for piece in chunk_text(text):
        yield format_text_delta(piece)
    yield format_text_end()
    yield format_finish_step()
    yield format_stream_finish()
    yield format_done()


def join_stream_preview(chunks: Iterable[str]) -> str:
    """Test helper: concatenate SSE payloads into one string."""
    return "".join(chunks)

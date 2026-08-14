"""SSE helpers for AI SDK-compatible chat streaming (text deltas).

Protocol note: Vercel AI SDK UI stream protocol uses Server-Sent Events where
text deltas are emitted as `data: {"type":"text-delta","delta":"..."}` lines
(plus start/finish framing). The frontend useChat transport will be aligned
to this stub when Step 10 lands; refine then against the pinned SDK version.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def format_text_delta(delta: str) -> str:
    return _sse({"type": "text-delta", "delta": delta})


def format_stream_start() -> str:
    return _sse({"type": "start"})


def format_stream_finish() -> str:
    return _sse({"type": "finish"})


def format_error(message: str) -> str:
    return _sse({"type": "error", "errorText": message})


def chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + size] for i in range(0, len(text), size)]


async def iter_canned_text_stream(text: str) -> AsyncIterator[str]:
    """Yield SSE frames for a canned assistant reply."""
    yield format_stream_start()
    for piece in chunk_text(text):
        yield format_text_delta(piece)
    yield format_stream_finish()


def join_stream_preview(chunks: Iterable[str]) -> str:
    """Test helper: concatenate SSE payloads into one string."""
    return "".join(chunks)

"""The URLs a turn's web search returned or opened, for grounding web citations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    NativeToolCallPart,
    NativeToolReturnPart,
)
from pydantic_ai.native_tools import WebSearchTool

from app.grounding import normalize_url


def web_urls(messages: Sequence[ModelMessage]) -> set[str]:
    """Comparison keys of every search result and opened page in these messages."""
    found: list[Any] = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, NativeToolCallPart) and part.tool_name == WebSearchTool.kind:
                found.append(_opened_url(part))
            elif (
                isinstance(part, NativeToolReturnPart)
                and part.tool_name == WebSearchTool.kind
            ):
                found.extend(_source_urls(part.content))
    keys = {normalize_url(url) for url in found if isinstance(url, str)}
    keys.discard(None)
    return keys  # type: ignore[return-value]


def _opened_url(call: NativeToolCallPart) -> Any:
    args = call.args_as_dict()
    return args.get("url") if args.get("type") == "open_page" else None


def _source_urls(content: Any) -> list[Any]:
    sources = content.get("sources") if isinstance(content, dict) else None
    if not isinstance(sources, list):
        return []
    return [source.get("url") for source in sources if isinstance(source, dict)]

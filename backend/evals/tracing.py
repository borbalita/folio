"""Langfuse for eval commands: required keys, the app's tracing setup, and a flush at the end."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langfuse import Langfuse, get_client

from app.config import settings
from app.observability import configure_tracing, shutdown_tracing


class LangfuseNotConfiguredError(RuntimeError):
    pass


@contextmanager
def eval_tracing() -> Iterator[Langfuse]:
    """Fail fast without Langfuse keys; otherwise trace like the app and flush on exit."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        raise LangfuseNotConfiguredError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required for eval runs"
        )
    configure_tracing()
    try:
        yield get_client()
    finally:
        shutdown_tracing()

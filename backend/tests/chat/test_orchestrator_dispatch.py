from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.exceptions import AgentRunError

from app.auth.dependencies import CurrentUser
from app.chat import orchestrator
from app.chat.orchestrator import run_turn
from app.database import chats
from app.email_assistant import STUB_REPLY
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

USER = CurrentUser(id=TEST_USER_ID, email="test@example.com")


def _collect(agent: str) -> str:
    async def _run() -> list[str]:
        frames: list[str] = []
        async for frame in run_turn(
            USER,
            TEST_THREAD_ID,
            [{"role": "user", "content": "hello"}],
            thread={
                "id": str(TEST_THREAD_ID),
                "title": "Thread",
                "agent": agent,
            },
        ):
            frames.append(frame)
        return frames

    return "".join(asyncio.run(_run()))


def test_email_thread_uses_stub_and_skips_document_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("document agent should not run")

    monkeypatch.setattr(orchestrator, "run_agent", fail)
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    assert "email assistant" in _collect("email")


def test_document_thread_uses_copilot(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def fail(*_args: object, **_kwargs: object) -> None:
        called.append("documents")
        raise AgentRunError("stop")

    monkeypatch.setattr(orchestrator, "run_agent", fail)
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    text = _collect("documents")

    assert called == ["documents"]
    assert STUB_REPLY not in text

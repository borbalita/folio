from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.exceptions import AgentRunError

from app.auth.dependencies import CurrentUser
from app.chat import orchestrator
from app.chat.orchestrator import ASSISTANT_UNAVAILABLE, run_turn
from app.database import chats
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


def test_email_thread_uses_email_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    async def email_agent(*_args: object, **_kwargs: object) -> None:
        called.append("email")
        raise AgentRunError("stop")

    def document_agent(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("document agent should not run")

    monkeypatch.setattr(orchestrator, "run_email_agent", email_agent)
    monkeypatch.setattr(orchestrator, "run_agent", document_agent)
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    text = _collect("email")

    assert called == ["email"]
    assert ASSISTANT_UNAVAILABLE in text


def test_document_thread_uses_copilot(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def fail(*_args: object, **_kwargs: object) -> None:
        called.append("documents")
        raise AgentRunError("stop")

    monkeypatch.setattr(orchestrator, "run_agent", fail)
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    text = _collect("documents")

    assert called == ["documents"]
    assert "email assistant isn't available" not in text


def test_finance_thread_replies_with_the_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no other agent should run")

    monkeypatch.setattr(orchestrator, "run_agent", fail)
    monkeypatch.setattr(orchestrator, "run_email_agent", fail)
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)

    assert "finance assistant" in _collect("finance")

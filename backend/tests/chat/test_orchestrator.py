from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest

from app.assistant.outputs import AgentTurnResult, Citation, GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import run_turn
from app.database import chats
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
USER = CurrentUser(id=TEST_USER_ID, email="test@example.com")


def _collect(messages: list[dict]) -> list[str]:
    async def _run() -> list[str]:
        return [frame async for frame in run_turn(USER, TEST_THREAD_ID, messages)]

    return asyncio.run(_run())


def _patch_chats(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(chats, "get_thread_for_user", lambda *_args, **_kwargs: {"id": str(TEST_THREAD_ID)})
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)
    append = MagicMock(
        return_value=[
            {"id": str(uuid.uuid4()), "role": "user"},
            {"id": str(uuid.uuid4()), "role": "assistant"},
        ],
    )
    monkeypatch.setattr(chats, "append_messages", append)
    monkeypatch.setattr(chats, "insert_citations", MagicMock())
    return append


def test_run_turn_streams_answer_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    append = _patch_chats(monkeypatch)

    async def fake_run(prompt: str, deps: object) -> AgentTurnResult:
        deps.seen_ids.add(A)  # type: ignore[attr-defined]
        return AgentTurnResult(
            answer=GroundedAnswer(
                answer="Services revenue increased.",
                citations=[Citation(chunk_id=A, citation_index=1, excerpt="Services revenue increased.")],
            ),
            usage={"requests": 1, "input_tokens": 10, "output_tokens": 5, "tool_calls": 1},
        )

    monkeypatch.setattr("app.chat.orchestrator.run_agent", fake_run)

    frames = _collect(
        [{"role": "user", "content": "How did Services do?"}],
    )
    joined = "".join(frames)

    assert "Services revenue increased." in joined
    assert "data-citation" in joined
    assert str(A) in joined
    append.assert_called_once()
    chats.insert_citations.assert_called_once()


def test_run_turn_grounding_error_does_not_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    append = _patch_chats(monkeypatch)

    async def fake_run(prompt: str, deps: object) -> AgentTurnResult:
        return AgentTurnResult(
            answer=GroundedAnswer(
                answer="Invented number.",
                citations=[Citation(chunk_id=A, citation_index=1)],
            ),
            usage={"requests": 1, "input_tokens": 1, "output_tokens": 1, "tool_calls": 0},
        )

    monkeypatch.setattr("app.chat.orchestrator.run_agent", fake_run)

    frames = _collect([{"role": "user", "content": "What is revenue?"}])
    joined = "".join(frames)

    assert "error" in joined
    assert "Invented number." not in joined
    append.assert_not_called()
    chats.insert_citations.assert_not_called()

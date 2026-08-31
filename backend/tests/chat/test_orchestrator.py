from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from app.assistant.agent import LOOKING_THROUGH_FILINGS
from app.assistant.grounding import UNKNOWN_CHUNK, GroundingError, grounding_user_answer
from app.assistant.outputs import AgentTurnResult, Citation, GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import ASSISTANT_UNAVAILABLE, UNEXPECTED_TURN_ERROR, run_turn
from app.chat.titles import DEFAULT_THREAD_TITLE
from app.database import chats
from app.retrieval.retriever import RetrievedPassage
from tests.conftest import TEST_THREAD_ID, TEST_USER_ID

A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
USER = CurrentUser(id=TEST_USER_ID, email="test@example.com")

PASSAGE = RetrievedPassage(
    chunk_id=A,
    document_id=uuid.UUID("00000000-0000-0000-0000-00000000000d"),
    chunk_index=0,
    text="Services revenue increased.",
    page="12",
    section="Item 1",
    fusion_score=0.02,
    ticker="AAPL",
    company_name="Apple Inc.",
    form="10-K",
    filing_date=date(2023, 11, 3),
    fiscal_year=2023,
    accession_number="0000320193-23-000106",
)


def _collect(messages: list[dict]) -> list[str]:
    async def _run() -> list[str]:
        return [frame async for frame in run_turn(USER, TEST_THREAD_ID, messages)]

    return asyncio.run(_run())


def _payloads(frames: list[str]) -> list[dict]:
    payloads: list[dict] = []
    for frame in frames:
        if not frame.startswith("data: "):
            continue
        raw = frame[len("data: ") :].strip()
        if raw == "[DONE]":
            continue
        payloads.append(json.loads(raw))
    return payloads


def _streamed_text(frames: list[str]) -> str:
    pieces: list[str] = []
    for frame in frames:
        if not frame.startswith("data: "):
            continue
        payload = frame[len("data: ") :].strip()
        if payload == "[DONE]":
            continue
        data = json.loads(payload)
        if data.get("type") == "text-delta":
            pieces.append(data["delta"])
    return "".join(pieces)


def _patch_chats(monkeypatch: pytest.MonkeyPatch, *, title: str = "Existing") -> MagicMock:
    monkeypatch.setattr(
        chats,
        "get_thread_for_user",
        lambda *_args, **_kwargs: {"id": str(TEST_THREAD_ID), "title": title},
    )
    monkeypatch.setattr(chats, "ensure_user", lambda *_args, **_kwargs: None)
    append = MagicMock(
        return_value=[
            {"id": str(uuid.uuid4()), "role": "user"},
            {"id": str(uuid.uuid4()), "role": "assistant"},
        ],
    )
    monkeypatch.setattr(chats, "append_messages", append)
    monkeypatch.setattr(chats, "insert_citations", MagicMock())
    monkeypatch.setattr(chats, "update_thread_title", MagicMock())
    return append


def test_run_turn_streams_answer_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    append = _patch_chats(monkeypatch)

    async def fake_run(prompt: str, deps: object) -> AgentTurnResult:
        deps.seen_ids.add(A)  # type: ignore[attr-defined]
        deps.seen_passages[A] = PASSAGE  # type: ignore[attr-defined]
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
    assert '"data":' in joined
    assert str(A) in joined
    assert '"companyName":"Apple Inc."' in joined
    assert '"filingDate":"2023-11-03"' in joined
    assert '"ticker":"AAPL"' in joined
    assert '"form":"10-K"' in joined
    append.assert_called_once()
    chats.insert_citations.assert_called_once()
    chats.update_thread_title.assert_not_called()


def test_run_turn_emits_search_status_before_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chats(monkeypatch)

    async def fake_run(prompt: str, deps: object) -> AgentTurnResult:
        await deps.status_queue.put("Looking through AAPL filings")  # type: ignore[attr-defined]
        deps.seen_ids.add(A)  # type: ignore[attr-defined]
        deps.seen_passages[A] = PASSAGE  # type: ignore[attr-defined]
        return AgentTurnResult(
            answer=GroundedAnswer(
                answer="Services revenue increased.",
                citations=[Citation(chunk_id=A, citation_index=1, excerpt="Services revenue increased.")],
            ),
            usage={"requests": 1, "input_tokens": 10, "output_tokens": 5, "tool_calls": 1},
        )

    monkeypatch.setattr("app.chat.orchestrator.run_agent", fake_run)

    frames = _collect([{"role": "user", "content": "How did Services do?"}])
    types = [payload["type"] for payload in _payloads(frames)]
    labels = [
        payload["data"]["label"]
        for payload in _payloads(frames)
        if payload.get("type") == "data-status"
    ]

    assert types[0] == "start"
    assert types.count("start") == 1
    assert types.index("start") < types.index("text-delta")
    assert LOOKING_THROUGH_FILINGS in labels
    assert "Looking through AAPL filings" in labels
    assert "Writing the answer" not in labels


def test_run_turn_grounding_error_streams_canned_answer(monkeypatch: pytest.MonkeyPatch) -> None:
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
    canned = grounding_user_answer(GroundingError(UNKNOWN_CHUNK, "internal"))

    assert _streamed_text(frames) == canned
    assert "Invented number." not in joined
    assert '"type":"error"' not in joined
    assert "data-citation" not in joined
    append.assert_called_once()
    chats.insert_citations.assert_not_called()
    chats.update_thread_title.assert_not_called()


def test_run_turn_titles_new_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chats(monkeypatch, title=DEFAULT_THREAD_TITLE)

    async def fake_run(prompt: str, deps: object) -> AgentTurnResult:
        deps.seen_ids.add(A)  # type: ignore[attr-defined]
        deps.seen_passages[A] = PASSAGE  # type: ignore[attr-defined]
        return AgentTurnResult(
            answer=GroundedAnswer(
                answer="Services revenue increased.",
                citations=[Citation(chunk_id=A, citation_index=1, excerpt="Services revenue increased.")],
            ),
            usage={"requests": 1, "input_tokens": 10, "output_tokens": 5, "tool_calls": 1},
        )

    monkeypatch.setattr("app.chat.orchestrator.run_agent", fake_run)
    monkeypatch.setattr(
        "app.chat.orchestrator.generate_thread_title",
        lambda question, answer: "AAPL Services FY2023",
    )

    _collect([{"role": "user", "content": "How did Services do?"}])

    chats.update_thread_title.assert_called_once_with(TEST_THREAD_ID, "AAPL Services FY2023")


def test_run_turn_grounding_titles_new_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chats(monkeypatch, title=DEFAULT_THREAD_TITLE)

    async def fake_run(prompt: str, deps: object) -> AgentTurnResult:
        return AgentTurnResult(
            answer=GroundedAnswer(
                answer="Invented number.",
                citations=[Citation(chunk_id=A, citation_index=1)],
            ),
            usage={"requests": 1, "input_tokens": 1, "output_tokens": 1, "tool_calls": 0},
        )

    monkeypatch.setattr("app.chat.orchestrator.run_agent", fake_run)
    monkeypatch.setattr(
        "app.chat.orchestrator.generate_thread_title",
        lambda question, answer: "Revenue question",
    )

    _collect([{"role": "user", "content": "What is revenue?"}])

    chats.update_thread_title.assert_called_once_with(TEST_THREAD_ID, "Revenue question")


def test_run_turn_agent_failure_streams_user_error(monkeypatch: pytest.MonkeyPatch) -> None:
    append = _patch_chats(monkeypatch)

    async def boom(prompt: str, deps: object) -> None:
        raise ModelHTTPError(status_code=429, model_name="gpt-5.5", body={"message": "no credits"})

    monkeypatch.setattr("app.chat.orchestrator.run_agent", boom)

    frames = _collect([{"role": "user", "content": "How did Services do?"}])
    payloads = _payloads(frames)
    errors = [payload for payload in payloads if payload.get("type") == "error"]

    assert errors == [{"type": "error", "errorText": ASSISTANT_UNAVAILABLE}]
    assert "no credits" not in "".join(frames)
    append.assert_not_called()
    chats.insert_citations.assert_not_called()


def test_run_turn_unexpected_error_streams_generic_user_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    append = _patch_chats(monkeypatch)

    async def boom(prompt: str, deps: object) -> None:
        raise RuntimeError("secret boom")

    monkeypatch.setattr("app.chat.orchestrator.run_agent", boom)

    frames = _collect([{"role": "user", "content": "How did Services do?"}])
    payloads = _payloads(frames)
    errors = [payload for payload in payloads if payload.get("type") == "error"]

    assert errors == [{"type": "error", "errorText": UNEXPECTED_TURN_ERROR}]
    assert "secret boom" not in "".join(frames)
    append.assert_not_called()

from __future__ import annotations

import uuid

from app.chat.messages import (
    StreamChatRequest,
    assistant_message_for_storage,
    extract_latest_user_text,
    user_message_for_storage,
)


def test_stream_chat_request_accepts_thread_id_alias() -> None:
    thread_id = uuid.uuid4()
    request = StreamChatRequest.model_validate(
        {"threadId": str(thread_id), "messages": []},
    )
    assert request.thread_id == thread_id


def test_extract_latest_user_text_from_content() -> None:
    messages = [
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "  What is revenue?  "},
    ]
    assert extract_latest_user_text(messages) == "What is revenue?"


def test_extract_latest_user_text_from_parts() -> None:
    messages = [
        {
            "role": "user",
            "parts": [
                {"type": "text", "text": "line one"},
                {"type": "text", "text": "line two"},
            ],
        },
    ]
    assert extract_latest_user_text(messages) == "line one\nline two"


def test_extract_latest_user_text_empty_when_no_user_message() -> None:
    assert extract_latest_user_text([{"role": "assistant", "content": "hi"}]) == ""


def test_user_message_for_storage_returns_last_user_message() -> None:
    first = {"role": "user", "content": "first"}
    second = {"role": "user", "content": "second"}
    assert user_message_for_storage([first, second]) == second


def test_user_message_for_storage_fallback() -> None:
    assert user_message_for_storage([]) == {"role": "user", "content": ""}


def test_assistant_message_for_storage_shape() -> None:
    stored = assistant_message_for_storage("answer")
    assert stored == {
        "role": "assistant",
        "content": "answer",
        "parts": [{"type": "text", "text": "answer"}],
    }

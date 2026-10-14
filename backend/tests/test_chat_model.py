from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai.models.openai import OpenAIResponsesModel

from app.assistant import agent as document_agent
from app.chat import titles
from app.chat_model import chat_model
from app.email_assistant import agent as email_agent


def test_chat_model_uses_the_responses_api_with_the_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.chat_model.settings.openai_chat_model", "gpt-6.1-sol")

    model = chat_model()

    assert isinstance(model, OpenAIResponsesModel)
    assert model.model_name == "gpt-6.1-sol"


@pytest.mark.parametrize(
    "build",
    [document_agent.get_agent, email_agent.get_agent, titles._title_agent],
    ids=["document", "email", "title"],
)
def test_every_chat_agent_uses_the_responses_api(build: Callable[[], Any]) -> None:
    build.cache_clear()  # type: ignore[attr-defined]
    try:
        assert isinstance(build().model, OpenAIResponsesModel)
    finally:
        build.cache_clear()  # type: ignore[attr-defined]

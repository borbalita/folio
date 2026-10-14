"""The chat model every agent runs on."""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings


def chat_model() -> OpenAIResponsesModel:
    # Responses, not Chat Completions: there GPT-6 models call tools only with reasoning off,
    # which GPT-6.1 Sol and Astra don't allow.
    return OpenAIResponsesModel(
        settings.openai_chat_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )

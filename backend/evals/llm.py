"""One structured OpenAI call, shared by the generation steps."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings

GENERATION_MODEL = "gpt-6.1-sol"


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, timeout=600)


def ask[T: BaseModel](model: str, system: str, user: str, schema: type[T]) -> T:
    completion = _client().chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError(f"{model} returned no parsable {schema.__name__}")
    return parsed

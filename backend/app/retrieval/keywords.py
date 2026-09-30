"""LLM keyword extraction for Postgres full-text search."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings


class FtsKeywords(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=5)


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def extract_fts_keywords(query: str, *, system_prompt: str) -> str:
    completion = _client().chat.completions.parse(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        response_format=FtsKeywords,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        return query
    terms = [term.strip() for term in parsed.keywords if term.strip()][:5]
    if not terms:
        return query
    return " ".join(terms)

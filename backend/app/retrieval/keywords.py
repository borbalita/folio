"""LLM keyword extraction for Postgres full-text search."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings

_SYSTEM_PROMPT = (
    "Extract 3 to 5 keywords for Postgres full-text search over SEC 10-K filings. "
    "Prefer company names, products, segments, and financial line items. "
    "No stopwords, no sentences, no punctuation."
)


class FtsKeywords(BaseModel):
    keywords: list[str] = Field(min_length=3, max_length=5)


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def extract_fts_keywords(query: str) -> str:
    completion = _client().chat.completions.parse(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        response_format=FtsKeywords,
        temperature=0,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        return query
    terms = [term.strip() for term in parsed.keywords if term.strip()][:5]
    if not terms:
        return query
    return " ".join(terms)

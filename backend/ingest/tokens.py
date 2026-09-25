"""Token limits and counting shared by filing and email ingest."""

from __future__ import annotations

from functools import lru_cache

import tiktoken

from app.config import settings

CHUNK_MAX_TOKENS = 512
# OpenAI embedding models accept at most 8192 tokens per input.
EMBEDDING_MAX_TOKENS = 8192


@lru_cache(maxsize=1)
def embedding_tokenizer() -> tiktoken.Encoding:
    return tiktoken.encoding_for_model(settings.openai_embedding_model)


def count_tokens(text: str) -> int:
    if not text:
        return 1
    return len(
        embedding_tokenizer().encode(
            text,
            allowed_special=set(),
            disallowed_special=(),
        ),
    )

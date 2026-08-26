"""OpenAI embedding helpers for ingestion."""

from __future__ import annotations

from openai import OpenAI

from app.config import settings
from ingest.chunking import EMBEDDING_MAX_TOKENS, count_tokens

EMBED_BATCH_SIZE = 100


def _assert_within_embedding_limit(texts: list[str]) -> None:
    for index, text in enumerate(texts):
        token_count = count_tokens(text)
        if token_count > EMBEDDING_MAX_TOKENS:
            msg = (
                f"chunk at index {index} has {token_count} tokens, "
                f"exceeding embedding limit of {EMBEDDING_MAX_TOKENS}"
            )
            raise ValueError(msg)


def embed_texts(texts: list[str], *, batch_size: int = EMBED_BATCH_SIZE) -> list[list[float]]:
    if not texts:
        return []

    _assert_within_embedding_limit(texts)

    client = OpenAI(api_key=settings.openai_api_key)
    vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(
            input=batch,
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        for item in ordered:
            if len(item.embedding) != settings.openai_embedding_dimensions:
                msg = (
                    "Unexpected embedding dimension "
                    f"{len(item.embedding)} != {settings.openai_embedding_dimensions}"
                )
                raise ValueError(msg)
            vectors.append(item.embedding)

    return vectors

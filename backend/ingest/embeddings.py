"""OpenAI embeddings for ingest batches and retrieval queries."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.config import settings

EMBED_BATCH_SIZE = 100


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(
    texts: list[str], *, batch_size: int = EMBED_BATCH_SIZE
) -> list[list[float]]:
    if not texts:
        return []

    expected_dims = settings.openai_embedding_dimensions
    vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = _client().embeddings.create(
            input=batch,
            model=settings.openai_embedding_model,
            dimensions=expected_dims,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        for item in ordered:
            if len(item.embedding) != expected_dims:
                msg = (
                    "Unexpected embedding dimension "
                    f"{len(item.embedding)} != {expected_dims}"
                )
                raise ValueError(msg)
            vectors.append(item.embedding)

    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]

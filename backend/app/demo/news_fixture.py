"""Load the demo news fixture: rephrased newsletter items with precomputed embeddings.

Each vector is stored as base64 of little-endian float32, which keeps the committed JSON
small. `embed_news_fixture` writes the file; the model and dimensions are stored with it so
a settings change is refused instead of mixing vector spaces.
"""

from __future__ import annotations

import base64
import json
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

DRAFT_PATH = Path(__file__).with_name("news_fixture.draft.json")
FIXTURE_PATH = Path(__file__).with_name("news_fixture.json")


@dataclass(frozen=True, slots=True)
class FixtureItem:
    key: str
    story: str
    source: str
    days_ago: int
    position: int
    title: str
    blurb: str
    url: str
    embedding: list[float]


def encode_vector(vector: list[float]) -> str:
    packed = array("f", vector)
    if sys.byteorder == "big":
        packed.byteswap()
    return base64.b64encode(packed.tobytes()).decode("ascii")


def decode_vector(encoded: str) -> list[float]:
    packed = array("f")
    packed.frombytes(base64.b64decode(encoded))
    if sys.byteorder == "big":
        packed.byteswap()
    return packed.tolist()


def load_fixture(path: Path = FIXTURE_PATH) -> list[FixtureItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["embedding_model"] != settings.openai_embedding_model:
        msg = (
            f"Fixture embedded with {data['embedding_model']}, "
            f"settings use {settings.openai_embedding_model}; rerun embed_news_fixture"
        )
        raise ValueError(msg)
    if data["embedding_dimensions"] != settings.openai_embedding_dimensions:
        msg = (
            f"Fixture has {data['embedding_dimensions']} dimensions, settings use "
            f"{settings.openai_embedding_dimensions}; rerun embed_news_fixture"
        )
        raise ValueError(msg)
    return [
        FixtureItem(**{**item, "embedding": decode_vector(item["embedding"])})
        for item in data["items"]
    ]

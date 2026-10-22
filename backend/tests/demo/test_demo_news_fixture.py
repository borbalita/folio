"""The demo news fixture: its text (from the draft) and its loader and embedding script."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from app.config import settings
from app.demo import embed_news_fixture, news_fixture
from app.demo.news_fixture import (
    FixtureItem,
    decode_vector,
    encode_vector,
    load_fixture,
)

DRAFT = json.loads(news_fixture.DRAFT_PATH.read_text(encoding="utf-8"))["items"]
SOURCES = {"demo_tensor", "demo_detective"}
SECURITY = re.compile(
    r"security|cyber|vulnerab|exploit|zero-day|\bCVEs?\b|breach|attack|certificate"
    r"|patch|threat|pen test",
    re.IGNORECASE,
)
NEW_MODEL = re.compile(
    r"\bmodel\b|\bGPT-\d|Gemini \d|Haiku \d|\bGLM\b|\bFlash\b|open-weights|open-sources",
    re.IGNORECASE,
)


def _text(item: dict) -> str:
    return f"{item['title']} {item['blurb']}"


def _write(path: Path, *, model: str | None = None, dims: int | None = None) -> None:
    dims = dims or settings.openai_embedding_dimensions
    items = [
        {
            "key": f"k{n}",
            "story": f"s{n}",
            "source": "demo_tensor",
            "days_ago": n,
            "position": 0,
            "title": f"Title {n}",
            "blurb": f"Blurb {n}",
            "url": f"https://example.com/{n}",
            "embedding": encode_vector([0.5 * (n + 1)] * dims),
        }
        for n in range(2)
    ]
    payload = {
        "embedding_model": model or settings.openai_embedding_model,
        "embedding_dimensions": dims,
        "items": items,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_draft_has_37_items_with_unique_keys():
    assert len(DRAFT) == 37
    assert len({i["key"] for i in DRAFT}) == 37


def test_draft_item_shape_and_sources():
    fields = {"key", "story", "source", "days_ago", "position", "title", "blurb", "url"}
    for item in DRAFT:
        assert set(item) == fields
        assert item["source"] in SOURCES
        assert item["url"].startswith("https://")
        assert item["title"].strip() and item["blurb"].strip()


def test_draft_positions_unique_per_source_and_day():
    slots = [(i["source"], i["days_ago"], i["position"]) for i in DRAFT]
    assert len(set(slots)) == len(slots)


def test_draft_big_and_multi_day_stories():
    sources = defaultdict(set)
    days = defaultdict(set)
    for item in DRAFT:
        sources[item["story"]].add(item["source"])
        days[item["story"]].add(item["days_ago"])
    assert sum(len(s) == 2 for s in sources.values()) >= 7
    assert sum(len(d) > 1 for d in days.values()) >= 3


def test_draft_has_security_and_new_model_news():
    assert sum(bool(SECURITY.search(_text(i))) for i in DRAFT) >= 5
    assert sum(bool(NEW_MODEL.search(_text(i))) for i in DRAFT) >= 5


def test_draft_has_no_tracking_or_newsletter_names():
    for item in DRAFT:
        assert "tldrnewsletter.com" not in item["url"]
        assert "utm_" not in item["url"]
        for field in ("title", "blurb", "url"):
            assert not re.search(r"tldr|alpha\s*signal", item[field], re.IGNORECASE)


def test_load_fixture_decodes_vectors(tmp_path):
    path = tmp_path / "fixture.json"
    _write(path)
    items = load_fixture(path)
    assert [i.key for i in items] == ["k0", "k1"]
    assert isinstance(items[0], FixtureItem)
    assert len(items[1].embedding) == settings.openai_embedding_dimensions
    assert items[1].embedding[0] == pytest.approx(1.0)
    assert items[0].title == "Title 0"


def test_load_fixture_refuses_other_model(tmp_path):
    path = tmp_path / "fixture.json"
    _write(path, model="some-other-model")
    with pytest.raises(ValueError, match="model"):
        load_fixture(path)


def test_load_fixture_refuses_other_dimensions(tmp_path):
    path = tmp_path / "fixture.json"
    _write(path, dims=settings.openai_embedding_dimensions + 1)
    with pytest.raises(ValueError, match="dimensions"):
        load_fixture(path)


def test_build_output_embeds_exactly_what_ingest_embeds():
    seen: list[str] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        seen.extend(texts)
        return [[float(n)] * 3 for n in range(len(texts))]

    out = embed_news_fixture.build_output(DRAFT, fake_embed)

    assert seen == [f"{i['title']}\n{i['blurb']}" for i in DRAFT]
    assert out["embedding_model"] == settings.openai_embedding_model
    assert out["embedding_dimensions"] == settings.openai_embedding_dimensions
    first = out["items"][0]
    assert {k: v for k, v in first.items() if k != "embedding"} == DRAFT[0]
    assert decode_vector(out["items"][2]["embedding"]) == [2.0, 2.0, 2.0]

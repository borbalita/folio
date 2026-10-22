"""One-off: embed the text-only draft and write `news_fixture.json` (costs a few cents).

Run from backend/: `uv run python -m app.demo.embed_news_fixture`. The text embedded is
`embed_text` from the news ingest, so the demo items match what a real edition would get.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from app.config import settings
from app.demo.news_fixture import DRAFT_PATH, FIXTURE_PATH, encode_vector
from ingest.email.news import ExtractedItem, embed_text
from ingest.embeddings import embed_texts


def build_output(
    draft_items: list[dict], embed: Callable[[list[str]], list[list[float]]]
) -> dict:
    texts = [
        embed_text(ExtractedItem(title=i["title"], blurb=i["blurb"], url=i["url"]))
        for i in draft_items
    ]
    vectors = embed(texts)
    return {
        "embedding_model": settings.openai_embedding_model,
        "embedding_dimensions": settings.openai_embedding_dimensions,
        "items": [
            {**item, "embedding": encode_vector(vector)}
            for item, vector in zip(draft_items, vectors, strict=True)
        ],
    }


def main() -> None:
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))["items"]
    output = build_output(draft, embed_texts)
    FIXTURE_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(draft)} items to {FIXTURE_PATH}")


if __name__ == "__main__":
    main()

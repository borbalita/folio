"""Embed the demo mail draft once. Run from backend/: uv run python -m app.demo.embed_mail_fixture

Writes mail_fixture.json next to the draft. Calls OpenAI once (40 short texts).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.demo.mail_dates import appointment_dates, render
from app.demo.mail_fixture import DRAFT_PATH, FIXTURE_PATH, REFERENCE_DAY, _rules
from app.demo.news_fixture import encode_vector


def chunk_text(subject: str, body: str) -> str:
    """The text the email pipeline embeds for a message (ingest/email/pipeline.py)."""
    return f"{subject}\n{body}"


def build_output(
    draft: dict[str, Any],
    embed: Callable[[list[str]], list[list[float]]],
    count_tokens: Callable[[str], int],
) -> dict[str, Any]:
    dates = appointment_dates(_rules(draft), REFERENCE_DAY)
    texts = [
        chunk_text(render(m["subject"], dates), render(m["body"], dates))
        for m in draft["emails"]
    ]
    vectors = embed(texts)
    emails = [
        {**mail, "embedding": encode_vector(vector), "token_count": count_tokens(text)}
        for mail, text, vector in zip(draft["emails"], texts, vectors, strict=True)
    ]
    return {
        "embedding_model": settings.openai_embedding_model,
        "embedding_dimensions": settings.openai_embedding_dimensions,
        "appointments": draft["appointments"],
        "emails": emails,
    }


def main() -> None:
    from ingest.email.pipeline import chunk_email_text
    from ingest.embeddings import embed_texts

    def count_tokens(text: str) -> int:
        pieces = chunk_email_text(text)
        if len(pieces) != 1:
            raise ValueError("Every demo email must fit one chunk")
        return pieces[0][1]

    output = build_output(json.loads(DRAFT_PATH.read_text()), embed_texts, count_tokens)
    FIXTURE_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=1))
    print(f"Wrote {len(output['emails'])} emails to {FIXTURE_PATH}")


if __name__ == "__main__":
    main()

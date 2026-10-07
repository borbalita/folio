"""Real AI newsletters for the extraction benchmark (plan 003), kept out of git."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel

from evals.dataset import DATA_ROOT

DEFAULT_NEWS_VERSION = "news-v1"
"""Default for the working-copy commands (export, local runs, review, sync)."""

SCORING_NEWS_VERSION = "news-v2"
"""Default dataset for `evals.run --mode extraction`: the current answer key (GPT-6 Astra)."""


class Newsletter(BaseModel):
    key: str
    """Stable within a version: n01, n02, ... in send order."""
    source: str
    sent_date: date
    subject: str
    body: str
    email_id: str
    """The app database row it was exported from, for tracing a result back."""


def news_dir(version: str) -> Path:
    return DATA_ROOT / version / "newsletters"


def load_newsletters(version: str) -> list[Newsletter]:
    return [
        Newsletter.model_validate_json(path.read_text())
        for path in sorted(news_dir(version).glob("n*.json"))
    ]
